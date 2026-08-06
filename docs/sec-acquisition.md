# SEC Acquisition Layer

The acquisition layer safely **retrieves and preserves** raw SEC EDGAR source
material. It is deliberately narrow: it fetches bytes and stores them immutably
with full provenance. It does **not** parse, normalize, or interpret any SEC
content — XBRL canonicalization, fact extraction, point-in-time resolution, and
everything downstream belong to later phases.

Package: `src/openfinance/sec/`.

## Architecture

Responsibilities are separated into single-purpose modules that compose into a
pipeline:

```
transport  →  retry/backoff + throttle  →  client  →  content-addressed store
```

| Module          | Responsibility                                                        |
| --------------- | --------------------------------------------------------------------- |
| `config.py`     | Immutable, environment-driven configuration (`SecConfig`).            |
| `transport.py`  | One HTTP round trip. `HttpTransport` protocol + `UrllibTransport`.    |
| `throttle.py`   | Client-side rate limiting (`RateLimiter`).                            |
| `retry.py`      | Exponential-backoff retries over a transport (`RetryingHttpClient`).  |
| `endpoints.py`  | Pure SEC URL construction and CIK canonicalization.                  |
| `artifacts.py`  | Artifact types, content hashing, and acquisition metadata.           |
| `storage.py`    | Content-addressed, immutable artifact storage (`ArtifactStore`).     |
| `client.py`     | The `SecClient` façade + submissions pagination.                     |
| `errors.py`     | Exception hierarchy rooted at `SecAcquisitionError`.                 |

The layers depend on interfaces, not concretions: the client holds a
`RetryingHttpClient`, which holds an `HttpTransport` *protocol*. Any transport
(including a test fake) can be injected, so the entire subsystem is testable
without touching the network.

The project has **zero runtime dependencies**; the transport uses only the
standard library (`urllib`).

## Configuration

All behaviour is configured from the environment. Nothing is hard-coded, and no
secrets are read or stored. Build a client with:

```python
from openfinance.sec import build_client

client = build_client()  # reads SecConfig.from_env()
```

Environment variables:

| Variable                        | Required | Default      | Meaning                                        |
| ------------------------------- | -------- | ------------ | ---------------------------------------------- |
| `OPENFINANCE_SEC_USER_AGENT`    | **yes**  | —            | Email-format contact identity (see below).     |
| `OPENFINANCE_SEC_STORAGE_DIR`   | no       | `./data/sec` | Root of the content-addressed store.           |
| `OPENFINANCE_SEC_MAX_RPS`       | no       | `8.0`        | Max requests/second (must be in `(0, 10]`).    |
| `OPENFINANCE_SEC_TIMEOUT`       | no       | `30.0`       | Per-request socket timeout in seconds.         |
| `OPENFINANCE_SEC_MAX_RETRIES`   | no       | `5`          | Additional attempts after the first (≥ 0).     |

Configuration is validated on construction (`ConfigError` on failure): the
User-Agent must be non-empty and contain `@`; the rate must be in `(0, 10]`;
timeout must be positive; retries must be non-negative.

## SEC access requirements

Reconnaissance across six issuers established two hard constraints:

- **`www.sec.gov` requires an email-format `User-Agent`** or it returns `403`.
  The Archives (filing index and documents) live on this host, so a valid
  contact identity is mandatory. `data.sec.gov` (the JSON APIs) is lenient, but
  we send the same identity everywhere.
- **Fair access is ≤ 10 requests/second.** The default rate is `8.0` to leave
  headroom for clock jitter across processes.

The User-Agent is contact information that SEC's fair-access policy asks clients
to disclose. **It is not a credential.** Set a real contact address you control;
do not commit a personal address to source (it belongs in the environment).

Every request advertises `Accept-Encoding: gzip`; gzipped bodies are inflated
transparently by the transport.

## Rate limiting

`RateLimiter` enforces a minimum interval (`1 / max_rps`) between successive
`acquire()` calls using a monotonic clock. It is a single-process gate; the
clock and sleep functions are injected so tests never actually sleep.

## Retry behaviour

`RetryingHttpClient` wraps a transport and the rate limiter:

- **Retried:** `429`, `500`, `502`, `503`, `504`, and transport-level failures
  (timeout, connection reset, DNS).
- **Not retried:** permanent client errors such as `403` and `404`. These are
  returned to the caller (the `SecClient` raises `HttpStatusError` for a
  non-`200`/`304`) rather than retried.
- **Backoff:** exponential with full jitter, capped at 30 s. A server-provided
  `Retry-After` (numeric form) is honoured in preference to computed backoff.
- **Budget:** at most `max_retries` additional attempts; once exhausted, a
  retryable status raises `HttpStatusError` and a persistent transport failure
  re-raises `TransportError`.

## Artifact identity

Artifact identity is the **SHA-256 of the retrieved bytes** — content
addressing. Consequences:

- The same bytes always have the same identity, regardless of when or from what
  URL they were fetched. Identity is never derived from timestamps or random
  UUIDs.
- Retrieval timestamps and other provenance are **descriptive only** and never
  part of identity. The retrieval clock is injected (`SecClient(clock=...)`) so
  identity is fully deterministic and reproducible.

## Storage layout

All under the configured storage root (default `./data/sec`):

```
blobs/<aa>/<full-sha256>            # immutable content-addressed bytes
meta/<artifact_type>/<sha256>.json  # one provenance record per content hash
```

- Blobs are sharded by the first two hex characters of the hash to keep
  directory sizes manageable.
- A blob's filename **is** its content hash, so it can never be overwritten with
  different bytes — a differing payload simply has a different name.
- Identical bytes fetched twice **deduplicate** to one blob (the second store
  reports `deduplicated=True`).
- Metadata lives beside blobs, keyed by content hash. Because one blob can be
  produced by several retrievals, each retrieval writes an (idempotent)
  metadata record without touching the immutable blob.

**Storage is outside Git by default.** The default root is under `data/`, which
`.gitignore` excludes; downloaded SEC datasets are never committed.

Each metadata record captures: source URL, artifact type, SHA-256, retrieval
timestamp, HTTP status, User-Agent (request identity for reproducibility),
content type, content length, `ETag`, `Last-Modified`, and the CIK/accession
when known.

## Artifact types

`ArtifactType` is the closed set of raw materials this layer retrieves:

`submissions`, `company_facts`, `filing_index`, `filing_document`,
`xbrl_instance`, `xbrl_schema`, `xbrl_calculation`, `xbrl_definition`,
`xbrl_label`, `xbrl_presentation`.

These are stored verbatim. `acquire_filing_document(...)` accepts an
`artifact_type` so callers can tag XBRL components precisely as they retrieve
them; the layer itself does not decide which file is which (no parsing).

## Pagination

The primary submissions response is **not** the complete filing history for
prolific filers — older filings spill onto overflow pages listed in
`filings.files[*].name` (JPMorgan required 69 pages during reconnaissance).
`iter_submissions_pages(cik)` fetches the primary page, reads those pointers,
and follows every overflow page, storing each as an immutable artifact:

```python
for page in client.iter_submissions_pages(320193):
    print(page.result.sha256, page.overflow_pages)
```

Reading the `filings.files` pointers is the only parsing the layer performs, and
it is confined to pagination; the page bytes are stored unmodified.

## Failure semantics

- **Interrupted / partial downloads never appear as valid artifacts.** Bytes are
  written to a temporary file, `fsync`'d, and only then atomically
  `os.replace`'d into their content-addressed path. A crash mid-write leaves at
  most a temp file, never a materialized blob.
- **Concurrent acquisition of the same blob is safe.** Temp files are
  per-process; the final rename is atomic and last-writer-wins is correct
  because all writers produce byte-identical content.
- **Corruption fails closed.** Storing bytes whose hash disagrees with the
  recorded SHA-256 raises `StorageError`; reading or deduplicating against an
  on-disk blob whose bytes no longer match its name raises
  `ArtifactConflictError`. The layer never silently overwrites.
- **Conditional requests.** When a prior artifact for the exact URL is known,
  the client sends `If-None-Match` / `If-Modified-Since`. A `304 Not Modified`
  reuses the stored bytes (recording fresh provenance against the unchanged
  hash) instead of re-downloading.

## Security considerations

- **No secrets.** The layer reads and stores no credentials. The only identity
  is the fair-access contact User-Agent, which is not a secret.
- **No hard-coded personal data.** The User-Agent must be supplied via the
  environment; construction fails otherwise. No personal email is baked into
  source.
- **Data stays out of Git.** The default storage root is git-ignored; SEC
  datasets are never committed.
- **Requests are GET-only** to public EDGAR endpoints over HTTPS.

## Example usage

```python
import os

from openfinance.sec import build_client

os.environ["OPENFINANCE_SEC_USER_AGENT"] = "OpenFinance you@example.com"
os.environ["OPENFINANCE_SEC_STORAGE_DIR"] = "/data/openfinance/sec"

client = build_client()

# Small metadata artifacts.
subs = client.acquire_submissions(320193)  # Apple
facts = client.acquire_company_facts(320193)
print(subs.sha256, subs.deduplicated)

# Full filing history, following overflow pages.
pages = list(client.iter_submissions_pages(320193))

# A filing package: index, then a tagged XBRL instance.
from openfinance.sec import ArtifactType

accession = "0000320193-18-000145"
client.acquire_filing_index(320193, accession)
client.acquire_filing_document(
    320193, accession, "aapl-20180929.xml", ArtifactType.XBRL_INSTANCE
)
```

## Testing

Unit tests (`tests/sec/`) inject a fake transport and a controllable clock, so
they are deterministic and **never depend on live SEC availability**. They cover
successful acquisition, SHA-256 identity, duplicate-content dedupe, interrupted
and corrupted storage, HTTP `403`/`429`/`5xx`, retry/backoff and `Retry-After`,
timeouts, User-Agent configuration, submissions pagination, atomic storage, and
conditional-request `304` reuse.

Run the full quality gate:

```bash
uv run pytest
uv run ruff check .
uv run mypy
uv build
```
