"""Tests for the urllib-based HTTP transport.

These exercise gzip handling and HTTP-error capture without real network I/O by
stubbing ``urllib.request.urlopen``.
"""

from __future__ import annotations

import gzip
import io
import urllib.error
from email.message import Message

import pytest

from openfinance.sec.errors import TransportError
from openfinance.sec.transport import HttpRequest, UrllibTransport


class _FakeResponse:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self.headers = _msg(headers)
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _msg(headers: dict[str, str]) -> Message:
    m = Message()
    for k, v in headers.items():
        m[k] = v
    return m


def test_successful_request_returns_body(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req: object, timeout: float) -> _FakeResponse:
        return _FakeResponse(200, {"Content-Type": "application/json"}, b"{}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    resp = UrllibTransport().send(HttpRequest("https://data.sec.gov/x"))
    assert resp.status == 200
    assert resp.body == b"{}"
    assert resp.header("content-type") == "application/json"


def test_gzip_body_is_inflated(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b'{"hello": "world"}'
    gz = gzip.compress(payload)

    def fake_urlopen(req: object, timeout: float) -> _FakeResponse:
        return _FakeResponse(200, {"Content-Encoding": "gzip"}, gz)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    resp = UrllibTransport().send(HttpRequest("https://data.sec.gov/x"))
    assert resp.body == payload


def test_http_error_status_is_returned_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(req: object, timeout: float) -> _FakeResponse:
        raise urllib.error.HTTPError(
            "https://www.sec.gov/x", 403, "Forbidden", _msg({}), io.BytesIO(b"nope")
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    resp = UrllibTransport().send(HttpRequest("https://www.sec.gov/x"))
    assert resp.status == 403
    assert resp.body == b"nope"


def test_network_failure_raises_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(req: object, timeout: float) -> _FakeResponse:
        raise urllib.error.URLError("connection reset")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(TransportError):
        UrllibTransport().send(HttpRequest("https://data.sec.gov/x"))


def test_timeout_raises_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req: object, timeout: float) -> _FakeResponse:
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(TransportError):
        UrllibTransport().send(HttpRequest("https://data.sec.gov/x"))


def test_gzip_requested_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_urlopen(req: object, timeout: float) -> _FakeResponse:
        captured.update(dict(req.headers))  # type: ignore[attr-defined]
        return _FakeResponse(200, {}, b"")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    UrllibTransport().send(HttpRequest("https://data.sec.gov/x"))
    # urllib title-cases header keys on the Request object.
    assert captured.get("Accept-encoding") == "gzip"
