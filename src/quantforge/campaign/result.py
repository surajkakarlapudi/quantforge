"""The sealed, content-addressed research-campaign-evaluation record (§9, §10).

A completed campaign evaluation is a :class:`ResearchCampaignEvaluation`: the
engine version, the full declarative request, the ordered ``(label,
walk_forward_evaluation_id, result_hash)`` reference to each trial (in request
order), the shared ``schedule_id`` and producing
``factor_portfolio_engine_version_id``, the per-trial statistic block (the OOS
Sharpe, skew, non-excess kurtosis, and Probabilistic Sharpe Ratio, each an
UNDEFINED-preserving :class:`~quantforge.campaign.model.StatValue`), the campaign
summary (the number of valid trials, the selected best trial, its Sharpe, the
population dispersion of the valid Sharpe ratios, the expected-maximum Sharpe under
the null, and the Deflated Sharpe Ratio), the carried-through corpus pins, and the
sealed ``result_hash`` over the computed answer.

Like every research record in this project it satisfies the
:class:`~quantforge.factors.store.ResearchRecord` Protocol - ``research_result_id``
aliases ``campaign_id`` (a single id, mirroring ``factor_risk_id``) and ``to_dict``
is deterministic - so it persists write-once to the shared Phase 8 sidecar with **no
new store** (§13). It stores only *pointers* to the referenced trials, never a copy
of their return series (the pointer-only discipline of
:class:`~quantforge.factorrisk.result.FactorRiskModel`): the referenced records already
live in the same sidecar, so this record stays a thin, reproducible index over them.

**Ex-post, not PIT (CE-6).** A selection-bias-corrected significance over realized
out-of-sample Sharpe ratios is an ex-post research statistic, not a forward-usable PIT
value. :class:`ResearchCampaignEvaluation` is deliberately **not** a ``Pit*`` type
and exposes **no** as-of accessor: it can never be handed to a layer that requires a
PIT signal. ``boundary_kind = "pit"`` documents only that the *underlying trials were
PIT walks* - the convention where the label describes the input side, not the ex-post
output.

Every value is deterministically serializable and round-trips byte-identically through
:meth:`~ResearchCampaignEvaluation.from_dict`; the derived ids are re-emitted by their
properties, never read from stored state, so a tampered stored id is ignored and
``from_dict(to_dict(r))`` re-emits identical bytes. No wall-clock, RNG, or
iteration-order dependence enters any value or id.
"""

from __future__ import annotations

from dataclasses import dataclass

from quantforge.campaign.identity import campaign_id as _campaign_id
from quantforge.campaign.identity import campaign_result_hash as _result_hash
from quantforge.campaign.model import StatValue, TrialStatus
from quantforge.campaign.version import CAMPAIGN_METHOD_VERSION

__all__ = [
    "BOUNDARY_PIT",
    "CAMPAIGN_RESULT_FORMAT_VERSION",
    "CampaignSummary",
    "ResearchCampaignEvaluation",
    "TrialStat",
]

#: The §9 record-schema version for the campaign record - distinct from the
#: engine-logic version, the method version, the normal-primitive version, and the
#: sidecar's container format version. Bump it when the serialized meaning of a
#: campaign record changes (a container concern; it is **not** folded into
#: ``campaign_id`` - §10, prior-phase discipline).
CAMPAIGN_RESULT_FORMAT_VERSION = "campaign-result/1"

#: The only boundary a v1 campaign record accepts. Walk-forward trials are PIT-only
#: by construction, so their OOS return series are PIT-only; the record carries this
#: explicit, un-defaulted value and the engine sets it unconditionally. It documents
#: the *input* side (the underlying trials were PIT walks); the campaign *output* is
#: ex-post and is not a PIT value (CE-6).
BOUNDARY_PIT = "pit"


# -- fail-closed decode helpers ----------------------------------------------


def _req_str(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _req_int(raw: dict[str, object], key: str) -> int:
    value = raw[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an int")
    return value


def _req_dict(raw: dict[str, object], key: str) -> dict[str, object]:
    value = raw[key]
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _req_list(raw: dict[str, object], key: str) -> list[object]:
    value = raw[key]
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _opt_str(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value


def _as_dict(value: object, key: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"each {key} entry must be an object")
    return value


def _as_str(value: object, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"each {key} entry must be a string")
    return value


def _trial_refs(items: list[object]) -> tuple[tuple[str, str, str], ...]:
    """Decode the ordered trial references into ``(label, id, result_hash)`` triples."""
    out: list[tuple[str, str, str]] = []
    for item in items:
        raw = _as_dict(item, "trial_refs")
        label = raw.get("label")
        if not isinstance(label, str):
            raise ValueError("each trial_refs entry must carry a string label")
        ref = raw.get("ref")
        if (
            not isinstance(ref, list)
            or len(ref) != 2
            or not all(isinstance(part, str) for part in ref)
        ):
            raise ValueError(
                "each trial_refs.ref must be an [id, result_hash] string pair"
            )
        out.append((label, ref[0], ref[1]))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class TrialStat:
    """One trial's sealed statistic block (§9).

    ``status`` is ``VALID`` when the OOS Sharpe is defined and ``UNDEFINED``
    otherwise; ``n`` is the OOS period count. ``sharpe`` / ``skew`` / ``kurtosis`` /
    ``psr`` are UNDEFINED-preserving cells - KNOWN canonical decimal strings for a
    valid trial (with a possibly-UNDEFINED ``psr`` when the Sharpe estimator is
    degenerate), all UNDEFINED with the trial's reason otherwise. Order in the record
    is the request order (the ``label`` is ``trial_1..trial_N``).
    """

    label: str
    status: TrialStatus
    n: int
    sharpe: StatValue
    skew: StatValue
    kurtosis: StatValue
    psr: StatValue

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "status": self.status.value,
            "n": self.n,
            "sharpe": self.sharpe.to_dict(),
            "skew": self.skew.to_dict(),
            "kurtosis": self.kurtosis.to_dict(),
            "psr": self.psr.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> TrialStat:
        status_raw = _req_str(raw, "status")
        try:
            status = TrialStatus(status_raw)
        except ValueError as exc:
            raise ValueError(f"unknown trial status {status_raw!r}") from exc
        return cls(
            label=_req_str(raw, "label"),
            status=status,
            n=_req_int(raw, "n"),
            sharpe=StatValue.from_dict(_req_dict(raw, "sharpe")),
            skew=StatValue.from_dict(_req_dict(raw, "skew")),
            kurtosis=StatValue.from_dict(_req_dict(raw, "kurtosis")),
            psr=StatValue.from_dict(_req_dict(raw, "psr")),
        )


@dataclass(frozen=True, slots=True)
class CampaignSummary:
    """The cross-trial selection-bias summary (§9).

    ``valid_trials`` is the count of trials with a defined Sharpe; ``selected_trial``
    is the ``trial_k`` label of the best trial (``None`` when the campaign is
    undefined for too few valid trials). ``selected_sharpe`` / ``sharpe_dispersion`` /
    ``expected_max_sharpe`` / ``deflated_sharpe`` are UNDEFINED-preserving cells -
    KNOWN for a defined campaign (with a possibly-UNDEFINED ``deflated_sharpe`` when
    the selected trial's PSR estimator is degenerate), all UNDEFINED with
    ``INSUFFICIENT_VALID_TRIALS`` otherwise.
    """

    valid_trials: int
    selected_trial: str | None
    selected_sharpe: StatValue
    sharpe_dispersion: StatValue
    expected_max_sharpe: StatValue
    deflated_sharpe: StatValue

    def to_dict(self) -> dict[str, object]:
        return {
            "valid_trials": self.valid_trials,
            "selected_trial": self.selected_trial,
            "selected_sharpe": self.selected_sharpe.to_dict(),
            "sharpe_dispersion": self.sharpe_dispersion.to_dict(),
            "expected_max_sharpe": self.expected_max_sharpe.to_dict(),
            "deflated_sharpe": self.deflated_sharpe.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> CampaignSummary:
        return cls(
            valid_trials=_req_int(raw, "valid_trials"),
            selected_trial=_opt_str(raw, "selected_trial"),
            selected_sharpe=StatValue.from_dict(_req_dict(raw, "selected_sharpe")),
            sharpe_dispersion=StatValue.from_dict(_req_dict(raw, "sharpe_dispersion")),
            expected_max_sharpe=StatValue.from_dict(
                _req_dict(raw, "expected_max_sharpe")
            ),
            deflated_sharpe=StatValue.from_dict(_req_dict(raw, "deflated_sharpe")),
        )


@dataclass(frozen=True, slots=True)
class ResearchCampaignEvaluation:
    """A sealed, content-addressed research-campaign-evaluation record (§9).

    Implements the :class:`~quantforge.factors.store.ResearchRecord` Protocol
    (:attr:`research_result_id` aliases :attr:`campaign_id`; deterministic
    :meth:`to_dict`), so it persists write-once to the shared research sidecar with no
    new store. It pins each trial by ``(label, walk_forward_evaluation_id,
    result_hash)`` in request order, records the shared schedule and producing engine
    version, holds the per-trial statistic block and the campaign summary, carries the
    referenced corpus pins, and seals the computed answer into ``result_hash`` - so its
    identity is a pure function of the request, the referenced content, and the
    computed statistics. It is **not** a ``Pit*`` type and exposes no as-of accessor
    (CE-6).
    """

    campaign_engine_version_id: str
    campaign_spec: dict[str, object]
    trial_refs: tuple[tuple[str, str, str], ...]
    boundary_kind: str
    schedule_id: str
    factor_portfolio_engine_version_id: str
    trials: tuple[TrialStat, ...]
    summary: CampaignSummary
    dataset_version_ids: tuple[str, ...]
    market_dataset_version_ids: tuple[str, ...]
    method_version: str
    result_hash: str

    # -- derived ids (never stored as state) ---------------------------------

    @property
    def campaign_id(self) -> str:
        """The content-addressed id - request, referenced content, **and** answer (§10).

        Re-derived from the record's own fields on every access (never read from
        stored state), so a tampered stored id is ignored and
        ``from_dict(to_dict(r))`` re-emits an identical id. Folds the engine version,
        the spec identity (extracted from the embedded request), the ordered trial
        ``result_hash``es, and the sealed ``result_hash`` over the computed answer.
        """
        spec = self.campaign_spec
        return _campaign_id(
            campaign_engine_version_id=self.campaign_engine_version_id,
            name=_spec_str(spec, "name"),
            spec_version=_spec_str(spec, "spec_version"),
            trial_ids=[ref[1] for ref in self.trial_refs],
            benchmark_sharpe=_spec_str(spec, "benchmark_sharpe"),
            trial_result_hashes=[ref[2] for ref in self.trial_refs],
            result_hash=self.result_hash,
        )

    @property
    def research_result_id(self) -> str:
        """Alias of :attr:`campaign_id` - the :class:`ResearchRecord` identity."""
        return self.campaign_id

    @property
    def trial_ids(self) -> tuple[str, ...]:
        """The referenced trial ids, in request order (fixes the labels and
        selection).
        """
        return tuple(ref[1] for ref in self.trial_refs)

    @property
    def pin_mismatch(self) -> bool:
        """True iff the trials differ on any carried corpus pin (§9).

        Surfaced, never raised (mirrors ``FactorRiskModel.pin_mismatch``): a campaign
        may legitimately evaluate trials run over a different corpus snapshot, but a
        reader must be able to see that the references were not pinned identically.
        (Commensurability - one ``schedule_id`` and one producing engine version - is a
        separate, *raised* contract.)
        """
        return (
            len(self.dataset_version_ids) > 1
            or len(self.market_dataset_version_ids) > 1
        )

    # -- sealing --------------------------------------------------------------

    @classmethod
    def seal(
        cls,
        *,
        campaign_engine_version_id: str,
        campaign_spec: dict[str, object],
        trial_refs: tuple[tuple[str, str, str], ...],
        boundary_kind: str,
        schedule_id: str,
        factor_portfolio_engine_version_id: str,
        trials: tuple[TrialStat, ...],
        summary: CampaignSummary,
        dataset_version_ids: tuple[str, ...],
        market_dataset_version_ids: tuple[str, ...],
        method_version: str = CAMPAIGN_METHOD_VERSION,
    ) -> ResearchCampaignEvaluation:
        """Seal computed blocks, folding the answer into ``result_hash`` (§10).

        The single constructor the engine uses: it folds the ordered computed-output
        cells (the per-trial statistic cells in request order, then the
        campaign-summary cell) into ``result_hash`` via
        :func:`~quantforge.campaign.identity.campaign_result_hash`, so identity is a
        pure function of the computed answer and never has to be supplied by the
        caller.
        """
        rhash = _result_hash(_output_cells(trials=trials, summary=summary))
        return cls(
            campaign_engine_version_id=campaign_engine_version_id,
            campaign_spec=dict(campaign_spec),
            trial_refs=trial_refs,
            boundary_kind=boundary_kind,
            schedule_id=schedule_id,
            factor_portfolio_engine_version_id=factor_portfolio_engine_version_id,
            trials=trials,
            summary=summary,
            dataset_version_ids=dataset_version_ids,
            market_dataset_version_ids=market_dataset_version_ids,
            method_version=method_version,
            result_hash=rhash,
        )

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            # The ResearchRecord alias so the generic sidecar reader keys correctly.
            "research_result_id": self.research_result_id,
            "campaign_engine_version_id": self.campaign_engine_version_id,
            "campaign_spec": dict(self.campaign_spec),
            "trial_refs": [
                {"label": label, "ref": [trial_id, result_hash]}
                for label, trial_id, result_hash in self.trial_refs
            ],
            "boundary_kind": self.boundary_kind,
            "schedule_id": self.schedule_id,
            "factor_portfolio_engine_version_id": (
                self.factor_portfolio_engine_version_id
            ),
            "trials": [trial.to_dict() for trial in self.trials],
            "summary": self.summary.to_dict(),
            "dataset_version_ids": list(self.dataset_version_ids),
            "market_dataset_version_ids": list(self.market_dataset_version_ids),
            "method_version": self.method_version,
            "result_hash": self.result_hash,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ResearchCampaignEvaluation:
        """Reconstruct a sealed campaign record from its :meth:`to_dict` payload.

        The additive inverse of :meth:`to_dict`, so a record read back from the shared
        sidecar via ``store.read_as(id, ResearchCampaignEvaluation.from_dict)`` is a
        first-class typed object. ``campaign_id`` / ``research_result_id`` are derived
        aliases re-emitted by their properties (never read from state), every nested
        cell round-trips through its own fail-closed ``from_dict``, and the block order
        is preserved - so ``from_dict(to_dict(r))`` re-emits identical bytes and the
        same ``result_hash``, introducing no drift.
        """
        return cls(
            campaign_engine_version_id=_req_str(raw, "campaign_engine_version_id"),
            campaign_spec=dict(_req_dict(raw, "campaign_spec")),
            trial_refs=_trial_refs(_req_list(raw, "trial_refs")),
            boundary_kind=_req_str(raw, "boundary_kind"),
            schedule_id=_req_str(raw, "schedule_id"),
            factor_portfolio_engine_version_id=_req_str(
                raw, "factor_portfolio_engine_version_id"
            ),
            trials=tuple(
                TrialStat.from_dict(_as_dict(item, "trials"))
                for item in _req_list(raw, "trials")
            ),
            summary=CampaignSummary.from_dict(_req_dict(raw, "summary")),
            dataset_version_ids=tuple(
                _as_str(item, "dataset_version_ids")
                for item in _req_list(raw, "dataset_version_ids")
            ),
            market_dataset_version_ids=tuple(
                _as_str(item, "market_dataset_version_ids")
                for item in _req_list(raw, "market_dataset_version_ids")
            ),
            method_version=_req_str(raw, "method_version"),
            result_hash=_req_str(raw, "result_hash"),
        )


def _output_cells(
    *,
    trials: tuple[TrialStat, ...],
    summary: CampaignSummary,
) -> list[dict[str, object]]:
    """The ordered computed-output cells sealed into ``result_hash`` (§10).

    A single deterministic list - the per-trial statistic cells in request order, then
    the single campaign-summary cell - each tagged by its block so two structurally
    different records can never collide, and each reduced to its canonical form.
    Sensitive to every computed statistic: one differing cell changes ``result_hash``
    and therefore ``campaign_id``.
    """
    cells: list[dict[str, object]] = []
    for trial in trials:
        cells.append(
            {
                "block": "trial",
                "label": trial.label,
                "status": trial.status.value,
                "n": trial.n,
                "sharpe": trial.sharpe.to_dict(),
                "skew": trial.skew.to_dict(),
                "kurtosis": trial.kurtosis.to_dict(),
                "psr": trial.psr.to_dict(),
            }
        )
    cells.append(
        {
            "block": "campaign",
            "valid_trials": summary.valid_trials,
            "selected_trial": summary.selected_trial,
            "selected_sharpe": summary.selected_sharpe.to_dict(),
            "sharpe_dispersion": summary.sharpe_dispersion.to_dict(),
            "expected_max_sharpe": summary.expected_max_sharpe.to_dict(),
            "deflated_sharpe": summary.deflated_sharpe.to_dict(),
        }
    )
    return cells


def _spec_str(spec: dict[str, object], key: str) -> str:
    """Read a required string field from the embedded request payload (fail closed)."""
    value = spec.get(key)
    if not isinstance(value, str):
        raise ValueError(f"campaign_spec.{key} must be a string")
    return value
