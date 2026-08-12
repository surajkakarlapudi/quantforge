"""The research-campaign-evaluation orchestration engine (§6, §12, CE-1..CE-6).

:class:`ResearchCampaignEngine` sits strictly **above** Phase 22: it is a pure
consumer that turns a declarative
:class:`~quantforge.campaign.spec.ResearchCampaignSpecification` into a sealed
:class:`~quantforge.campaign.result.ResearchCampaignEvaluation` by *resolving* the
ordered set of ``N`` already-sealed
:class:`~quantforge.walkforward.result.WalkForwardEvaluation` records a request names
(the "trials" of one research campaign), *verifying* each one, *enforcing* that the
trials are commensurable (one shared rebalance schedule and one producing
factor-portfolio engine version, so their out-of-sample Sharpe ratios are drawn from
one comparable search), *estimating* each trial's OOS excess-return moments and its
Probabilistic Sharpe Ratio against the benchmark (Phase 23 method), *selecting* the
best OOS Sharpe, *estimating* the expected-maximum Sharpe under the null, *deflating*
the best trial's significance for the size of the search (the Deflated Sharpe Ratio),
and sealing the answer. It introduces no new data-resolution logic, no new PIT
surface, and no new store; it composes the pinned pure functions of
:mod:`quantforge.campaign.moments` / :mod:`quantforge.campaign.compute` /
:mod:`quantforge.campaign.normal` and persists write-once to the shared research
sidecar (§6, §13, §16).

The build (§6):

1. **Resolve** each ``trial_id`` from the shared sidecar via ``store.read_as(id,
   WalkForwardEvaluation.from_dict)``, in request order. A missing id (or a payload that
   does not decode as a ``WalkForwardEvaluation``) is a consistency defect and raises
   :class:`~quantforge.campaign.errors.CampaignConsistencyError` (fail closed, CE-1).
2. **Verify** each trial: its ``research_result_id`` equals the requested id and its
   roll-up ``status`` is ``REALIZED`` (a walk that sealed no defensible OOS series is
   not a campaign trial). Each violation raises (CE-1/CE-3).
3. **Enforce commensurability** (CE-3): every trial shares one ``schedule_id`` and one
   ``factor_portfolio_engine_version_id`` - otherwise the OOS Sharpe ratios are not
   drawn from one comparable search and a cross-trial selection-bias correction is
   meaningless. A disagreement raises.
4. **Estimate per-trial statistics** (§12): from each trial's chained OOS return
   series and its own inherited ``risk_free_per_period``, compute the per-period
   Sharpe, skew, non-excess kurtosis (Phase 23 moment method) and the Probabilistic
   Sharpe Ratio against the request benchmark. A trial with fewer than two OOS periods,
   a zero-variance OOS series, or a degenerate Sharpe estimator is a first-class
   UNDEFINED cell, never raised (CE-4).
5. **Select + deflate** (§12): ``N`` is the count of **all** submitted trials (CE-2);
   the greatest-Sharpe valid trial is selected (ties → lowest index); the
   expected-maximum Sharpe ``SR₀`` is estimated from the valid trials' Sharpe
   dispersion; the Deflated Sharpe Ratio is the selected trial's PSR against ``SR₀``. A
   campaign with fewer than
   :data:`~quantforge.campaign.compute.MIN_VALID_TRIALS` valid trials records the
   selection / ``SR₀`` / DSR as UNDEFINED ``INSUFFICIENT_VALID_TRIALS`` (CE-4), never
   raised.
6. **Seal + persist**: seal a
   :class:`~quantforge.campaign.result.ResearchCampaignEvaluation`
   (its ``result_hash`` folds the answer) and persist it write-once to the same
   sidecar. Rebuilding an identical request is a byte-identical no-op; a differing
   payload under the same id fails closed via the store's guard.

The engine holds no mutable per-run state - a build's state lives entirely in local
variables, so one engine can compute many records and two builds of the same spec over
the same immutable sidecar are byte-identical.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Context, Decimal, localcontext

from quantforge.campaign.compute import (
    CampaignComputation,
    TrialComputation,
    campaign_statistics,
    trial_statistics,
)
from quantforge.campaign.errors import (
    CampaignConfigurationError,
    CampaignConsistencyError,
)
from quantforge.campaign.model import (
    CampaignUndefinedReason,
    StatValue,
    TrialStatus,
    trial_label,
)
from quantforge.campaign.moments import TrialMoments, trial_moments
from quantforge.campaign.result import (
    BOUNDARY_PIT,
    CampaignSummary,
    ResearchCampaignEvaluation,
    TrialStat,
)
from quantforge.campaign.spec import ResearchCampaignSpecification
from quantforge.campaign.version import CampaignEngineVersion
from quantforge.factors.store import ResearchResultStore
from quantforge.walkforward.model import WindowStatus
from quantforge.walkforward.result import WalkForwardEvaluation
from quantforge.workspace import Workspace

__all__ = ["ResearchCampaignEngine"]


class ResearchCampaignEngine:
    """Resolve, verify, estimate, select, deflate, and seal a campaign request (§6).

    Constructed from a :class:`~quantforge.workspace.Workspace` (the composition root);
    it reuses the workspace's shared Phase 8 research sidecar - the same store the
    walk-forward engine sealed its evaluations to - so a request evaluates exactly the
    trials already present. The sidecar may be overridden (for tests). The engine pins
    its orchestration logic + statistical method + normal primitive + decimal context
    via :class:`CampaignEngineVersion`, and computes every value under that version's
    decimal context.
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        research_store: ResearchResultStore | None = None,
        version: CampaignEngineVersion | None = None,
    ) -> None:
        self._workspace = workspace
        self._research_store = research_store
        self._version = version if version is not None else CampaignEngineVersion()

    @property
    def campaign_engine_version_id(self) -> str:
        """The orchestration + method + normal + decimal-context version, folded in."""
        return self._version.campaign_engine_version_id

    @property
    def research_store(self) -> ResearchResultStore:
        """The write-once sidecar the evaluation resolves from and persists to."""
        if self._research_store is not None:
            return self._research_store
        store = self._workspace.research_result_store
        assert isinstance(store, ResearchResultStore)
        return store

    def evaluate(
        self, spec: ResearchCampaignSpecification
    ) -> ResearchCampaignEvaluation:
        """Resolve, verify, estimate, select, deflate, seal, persist (§6).

        Deterministic and reproducible: the same spec over the same immutable sidecar
        re-resolves the same trials, recomputes byte-identical statistics under the
        pinned decimal context, and seals a byte-identical
        :class:`~quantforge.campaign.result.ResearchCampaignEvaluation` on any machine
        (whose sidecar write is an idempotent no-op). Fails closed on a missing /
        drifted reference, a non-``WalkForwardEvaluation`` record, a non-REALIZED trial,
        or incommensurable trials; a trial with too few OOS periods, a zero-variance OOS
        series, or a degenerate Sharpe estimator (and a campaign with too few valid
        trials) is recorded as a first-class UNDEFINED cell (CE-4), never raised.
        """
        if not isinstance(spec, ResearchCampaignSpecification):
            raise CampaignConfigurationError(
                "evaluate() requires a ResearchCampaignSpecification"
            )

        store = self.research_store
        context = self._version.decimal_context()

        # -- resolve + verify each trial, in request order (CE-1/CE-3) --------
        trials = [self._resolve_trial(trial_id, store) for trial_id in spec.trial_ids]
        schedule_id, factor_engine_version_id = self._verify_commensurable(
            spec.trial_ids, trials
        )

        # -- per-trial moments + statistics (Phase 23 method; CE-4) -----------
        with localcontext(context):
            benchmark = +Decimal(spec.benchmark_sharpe)
        moments: list[TrialMoments] = [
            trial_moments(
                trial.oos_returns,
                risk_free_per_period=trial.risk_free_per_period,
                context=context,
            )
            for trial in trials
        ]
        computations = trial_statistics(moments, benchmark=benchmark, context=context)

        # -- select the best trial + deflate for the search size (CE-2) -------
        campaign = campaign_statistics(
            computations, n_trials=len(trials), context=context
        )

        # -- assemble the sealed blocks ---------------------------------------
        trial_stats = tuple(
            self._trial_stat(computation, context) for computation in computations
        )
        summary = self._summary(campaign, context)
        trial_refs = tuple(
            (trial_label(index), trial.research_result_id, trial.result_hash)
            for index, trial in enumerate(trials)
        )
        dataset_version_ids = self._distinct(
            trial.dataset_version_ids for trial in trials
        )
        market_dataset_version_ids = self._distinct(
            trial.market_dataset_version_ids for trial in trials
        )

        # -- seal + persist ---------------------------------------------------
        evaluation = ResearchCampaignEvaluation.seal(
            campaign_engine_version_id=self._version.campaign_engine_version_id,
            campaign_spec=spec.to_dict(),
            trial_refs=trial_refs,
            boundary_kind=BOUNDARY_PIT,
            schedule_id=schedule_id,
            factor_portfolio_engine_version_id=factor_engine_version_id,
            trials=trial_stats,
            summary=summary,
            dataset_version_ids=dataset_version_ids,
            market_dataset_version_ids=market_dataset_version_ids,
            method_version=self._version.method_version,
        )
        # Persist write-once to the shared research sidecar. Idempotent for a
        # byte-identical re-build; a differing payload under the same id raises there.
        store.write(evaluation)
        return evaluation

    # -- resolution & verification -------------------------------------------

    def _resolve_trial(
        self, trial_id: str, store: ResearchResultStore
    ) -> WalkForwardEvaluation:
        """Read + verify one referenced walk-forward trial (fail closed, CE-1/CE-3)."""
        try:
            result = store.read_as(trial_id, WalkForwardEvaluation.from_dict)
        except (KeyError, ValueError) as exc:
            raise CampaignConsistencyError(
                f"trial {trial_id!r} could not be decoded as a WalkForwardEvaluation; "
                "the referenced artifact is absent or not a walk-forward evaluation "
                "(fail closed)"
            ) from exc
        if result is None:
            raise CampaignConsistencyError(
                f"trial {trial_id!r} is not present in the research sidecar; cannot "
                "evaluate a campaign trial that was never sealed (fail closed)"
            )
        if result.research_result_id != trial_id:
            raise CampaignConsistencyError(
                f"trial {trial_id!r} resolved to a record whose id "
                f"{result.research_result_id!r} disagrees with the request; the "
                "sidecar is inconsistent (fail closed)"
            )
        if result.status is not WindowStatus.REALIZED:
            raise CampaignConsistencyError(
                f"trial {trial_id!r} has roll-up status {result.status.value!r}, not "
                "REALIZED; it sealed no defensible out-of-sample series to enter into "
                "a campaign (fail closed)"
            )
        return result

    def _verify_commensurable(
        self,
        trial_ids: tuple[str, ...],
        trials: list[WalkForwardEvaluation],
    ) -> tuple[str, str]:
        """The shared ``(schedule_id, factor_portfolio_engine_version_id)`` (CE-3).

        Every trial must share one rebalance schedule and one producing factor-portfolio
        engine version - otherwise their out-of-sample Sharpe ratios are not drawn from
        one comparable search and a cross-trial selection-bias correction would be
        meaningless. A disagreement is a consistency defect, raised rather than silently
        computed around.
        """
        schedule_id = trials[0].schedule_id
        factor_engine_version_id = trials[0].factor_portfolio_engine_version_id
        for trial_id, trial in zip(trial_ids[1:], trials[1:], strict=True):
            if trial.schedule_id != schedule_id:
                raise CampaignConsistencyError(
                    f"trial {trial_id!r} uses rebalance schedule "
                    f"{trial.schedule_id!r} but the first trial uses {schedule_id!r}; "
                    "a campaign requires one shared schedule so the trials are "
                    "comparable (fail closed, CE-3)"
                )
            if trial.factor_portfolio_engine_version_id != factor_engine_version_id:
                raise CampaignConsistencyError(
                    f"trial {trial_id!r} was produced by factor-portfolio engine "
                    f"{trial.factor_portfolio_engine_version_id!r} but the first trial "
                    f"by {factor_engine_version_id!r}; a campaign requires one "
                    "producing engine version so the trials are comparable (fail "
                    "closed, CE-3)"
                )
        return schedule_id, factor_engine_version_id

    # -- assembly -------------------------------------------------------------

    def _trial_stat(self, computation: TrialComputation, context: Context) -> TrialStat:
        """Map a computed trial into its sealed :class:`TrialStat` block.

        A VALID trial emits KNOWN canonical decimal cells for Sharpe / skew /
        kurtosis and a KNOWN PSR (or an UNDEFINED ``DEGENERATE_SHARPE_ESTIMATOR``
        PSR); an UNDEFINED trial emits every cell as UNDEFINED carrying the trial's
        reason.
        """
        label = trial_label(computation.index)
        if computation.status is TrialStatus.UNDEFINED:
            assert computation.reason is not None  # UNDEFINED ⇒ reason present
            cell = StatValue.undefined(computation.reason)
            return TrialStat(
                label=label,
                status=TrialStatus.UNDEFINED,
                n=computation.n,
                sharpe=cell,
                skew=cell,
                kurtosis=cell,
                psr=cell,
            )
        assert computation.sharpe is not None
        assert computation.skew is not None
        assert computation.kurtosis is not None
        return TrialStat(
            label=label,
            status=TrialStatus.VALID,
            n=computation.n,
            sharpe=self._known(computation.sharpe, context),
            skew=self._known(computation.skew, context),
            kurtosis=self._known(computation.kurtosis, context),
            psr=self._cell(computation.psr, computation.psr_reason, context),
        )

    def _summary(
        self, campaign: CampaignComputation, context: Context
    ) -> CampaignSummary:
        """Map the computed campaign into its sealed :class:`CampaignSummary` block.

        A defined campaign emits the selected ``trial_k`` label and KNOWN cells for the
        selected Sharpe, the Sharpe dispersion, and the expected-maximum Sharpe (with a
        KNOWN or degenerate-UNDEFINED Deflated Sharpe Ratio); an undefined campaign (too
        few valid trials) emits no selection and every cell UNDEFINED
        ``INSUFFICIENT_VALID_TRIALS``.
        """
        if campaign.reason is not None:
            cell = StatValue.undefined(campaign.reason)
            return CampaignSummary(
                valid_trials=campaign.valid_count,
                selected_trial=None,
                selected_sharpe=cell,
                sharpe_dispersion=cell,
                expected_max_sharpe=cell,
                deflated_sharpe=cell,
            )
        assert campaign.selected_index is not None
        assert campaign.selected_sharpe is not None
        assert campaign.dispersion is not None
        assert campaign.expected_max_sharpe is not None
        return CampaignSummary(
            valid_trials=campaign.valid_count,
            selected_trial=trial_label(campaign.selected_index),
            selected_sharpe=self._known(campaign.selected_sharpe, context),
            sharpe_dispersion=self._known(campaign.dispersion, context),
            expected_max_sharpe=self._known(campaign.expected_max_sharpe, context),
            deflated_sharpe=self._cell(
                campaign.deflated_sharpe, campaign.deflated_reason, context
            ),
        )

    def _known(self, value: Decimal, context: Context) -> StatValue:
        """A KNOWN cell holding the canonical decimal string of ``value``.

        Canonicalized via ``str(+value)`` **inside** the pinned context, so the ambient
        (precision-28) default context can never silently re-round the sealed string.
        """
        with localcontext(context):
            return StatValue.known(str(+value))

    def _cell(
        self,
        value: Decimal | None,
        reason: CampaignUndefinedReason | None,
        context: Context,
    ) -> StatValue:
        """A KNOWN cell for a computed value, or an UNDEFINED cell carrying
        ``reason``.
        """
        if value is not None:
            return self._known(value, context)
        assert reason is not None  # value is None ⇒ a reason was recorded
        return StatValue.undefined(reason)

    def _distinct(self, groups: Iterable[tuple[str, ...]]) -> tuple[str, ...]:
        """The sorted distinct union of several string tuples (deterministic).

        Trials may legitimately have been run over different corpus snapshots; the
        record carries the sorted distinct union of their pins so a reader can detect
        (via
        :attr:`~quantforge.campaign.result.ResearchCampaignEvaluation.pin_mismatch`)
        that the references were not pinned identically. Sorted for a stable,
        order-independent serialization.
        """
        seen: set[str] = set()
        for group in groups:
            seen.update(group)
        return tuple(sorted(seen))
