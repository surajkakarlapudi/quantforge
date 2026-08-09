"""Experiment specification: identity, expansion, and fail-closed validation.

Covers the declarative sweep half of Phase 13 (locked §3.1, §3.2, §4, D2, D7): axis and
experiment identity determinism, sweep-expansion determinism, closed-vocabulary
enforcement, duplicate/invalid values, and verbatim corpus pinning across children.
"""

from __future__ import annotations

import pytest

from quantforge.backtest.schedule import RebalanceSchedule
from quantforge.backtest.spec import CostModel
from quantforge.experiment.errors import ExperimentConfigurationError
from quantforge.experiment.spec import (
    SWEEPABLE_PARAMETERS,
    ExperimentSpecification,
    SweepAxis,
)
from quantforge.metrics.model import MetricPeriod
from tests.experiment.builders import (
    alt_schedule,
    base_spec,
    populate,
    select_n_axis,
)


class TestSweepAxisIdentity:
    def test_axis_id_is_deterministic(self) -> None:
        assert SweepAxis("select_n", (1, 2)).sweep_axis_id == (
            SweepAxis("select_n", (1, 2)).sweep_axis_id
        )

    def test_axis_id_is_value_order_independent(self) -> None:
        # A set identity: axis-value order never changes the id (locked §4).
        assert (
            SweepAxis("select_n", (1, 2, 3)).sweep_axis_id
            == SweepAxis("select_n", (3, 1, 2)).sweep_axis_id
        )

    def test_axis_id_is_membership_sensitive(self) -> None:
        assert (
            SweepAxis("select_n", (1, 2)).sweep_axis_id
            != SweepAxis("select_n", (1, 3)).sweep_axis_id
        )

    def test_axis_id_is_parameter_sensitive(self) -> None:
        # Same canonical value strings, different parameter → distinct id.
        assert (
            SweepAxis("cost_model.proportional_bps", ("1", "2")).sweep_axis_id
            != SweepAxis("cost_model.fixed_per_order", ("1", "2")).sweep_axis_id
        )

    def test_leading_zeros_canonicalize(self) -> None:
        # Decimal parsing folds "007" and "7" to the same canonical string, matching
        # the backtest layer's ``str(Decimal(...))`` convention (scale is preserved, so
        # "5" and "5.0" stay distinct, but insignificant leading zeros do not).
        assert (
            SweepAxis("cost_model.proportional_bps", ("007",)).sweep_axis_id
            == SweepAxis("cost_model.proportional_bps", ("7",)).sweep_axis_id
        )


class TestFailClosed:
    def test_parameter_outside_vocabulary_is_rejected(self) -> None:
        with pytest.raises(ExperimentConfigurationError, match="closed v1"):
            SweepAxis("sharpe_target", (1,))

    def test_empty_axis_is_rejected(self) -> None:
        with pytest.raises(ExperimentConfigurationError, match="at least one value"):
            SweepAxis("select_n", ())

    def test_duplicate_axis_value_is_rejected(self) -> None:
        with pytest.raises(ExperimentConfigurationError, match="duplicate"):
            SweepAxis("select_n", (1, 1))

    def test_duplicate_by_canonical_form_is_rejected(self) -> None:
        # "007" and "7" fold to one canonical decimal — a duplicate, not two values.
        with pytest.raises(ExperimentConfigurationError, match="duplicate"):
            SweepAxis("cost_model.proportional_bps", ("007", "7"))

    def test_wrong_type_for_select_n_is_rejected(self) -> None:
        with pytest.raises(ExperimentConfigurationError, match="positive int"):
            SweepAxis("select_n", ("1",))

    def test_nonpositive_select_n_is_rejected(self) -> None:
        with pytest.raises(ExperimentConfigurationError, match="positive int"):
            SweepAxis("select_n", (0,))

    def test_bool_is_not_an_int_for_select_n(self) -> None:
        with pytest.raises(ExperimentConfigurationError, match="positive int"):
            SweepAxis("select_n", (True,))

    def test_bad_rank_direction_is_rejected(self) -> None:
        with pytest.raises(ExperimentConfigurationError, match="one of"):
            SweepAxis("rank", ("sideways",))

    def test_negative_cost_is_rejected(self) -> None:
        with pytest.raises(ExperimentConfigurationError, match="negative"):
            SweepAxis("cost_model.proportional_bps", ("-1",))

    def test_zero_initial_capital_is_rejected(self) -> None:
        with pytest.raises(ExperimentConfigurationError, match="strictly positive"):
            SweepAxis("initial_capital", ("0",))

    def test_non_metric_period_is_rejected(self) -> None:
        with pytest.raises(ExperimentConfigurationError, match="MetricPeriod"):
            SweepAxis("period", ("2023-09-30",))

    def test_non_schedule_is_rejected(self) -> None:
        with pytest.raises(ExperimentConfigurationError, match="RebalanceSchedule"):
            SweepAxis("schedule", ("2024-01-15T00:00:00Z",))

    def test_all_vocabulary_parameters_are_constructible(self) -> None:
        # Every closed-vocabulary parameter has a valid representative value.
        reps: dict[str, object] = {
            "select_n": 1,
            "rank": "descending",
            "signal": "current_ratio",
            "period": MetricPeriod.instant("2023-09-30"),
            "cost_model.proportional_bps": "5",
            "cost_model.fixed_per_order": "1",
            "schedule": RebalanceSchedule.of(["2024-01-15T00:00:00Z"]),
            "initial_capital": "1000000",
        }
        for parameter in SWEEPABLE_PARAMETERS:
            if parameter == "universe":
                continue  # exercised in the expansion tests (needs a real spec)
            SweepAxis(parameter, (reps[parameter],))


class TestExperimentValidation:
    def _pop(self, tmp_path: object):  # type: ignore[no-untyped-def]
        from pathlib import Path

        assert isinstance(tmp_path, Path)
        return populate(tmp_path)

    def test_empty_name_is_rejected(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = self._pop(tmp_path)
        with pytest.raises(ExperimentConfigurationError, match="non-empty name"):
            ExperimentSpecification(
                name="", base=base_spec(corpus), axes=(select_n_axis(),)
            )

    def test_zero_axis_experiment_is_rejected(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = self._pop(tmp_path)
        with pytest.raises(
            ExperimentConfigurationError, match="at least one sweep axis"
        ):
            ExperimentSpecification(name="e", base=base_spec(corpus), axes=())

    def test_two_axes_on_one_parameter_is_rejected(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = self._pop(tmp_path)
        with pytest.raises(ExperimentConfigurationError, match="same parameter"):
            ExperimentSpecification(
                name="e",
                base=base_spec(corpus),
                axes=(select_n_axis(1, 2), select_n_axis(3, 4)),
            )

    def test_unpinned_base_is_rejected(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        self._pop(tmp_path)
        with pytest.raises(ExperimentConfigurationError, match="BacktestSpecification"):
            ExperimentSpecification(
                name="e",
                base=object(),  # type: ignore[arg-type]
                axes=(select_n_axis(),),
            )


class TestIdentitySensitivity:
    def test_experiment_id_is_deterministic(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        spec_a = ExperimentSpecification(
            name="e", base=base_spec(corpus), axes=(select_n_axis(1, 2),)
        )
        spec_b = ExperimentSpecification(
            name="e", base=base_spec(corpus), axes=(select_n_axis(2, 1),)
        )
        assert spec_a.experiment_id(
            risk_free_per_period="0", periods_per_year="1"
        ) == spec_b.experiment_id(risk_free_per_period="0", periods_per_year="1")

    def test_experiment_id_is_name_sensitive(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        base = base_spec(corpus)
        a = ExperimentSpecification(name="alpha", base=base, axes=(select_n_axis(),))
        b = ExperimentSpecification(name="beta", base=base, axes=(select_n_axis(),))
        assert a.experiment_id(risk_free_per_period="0", periods_per_year="1") != (
            b.experiment_id(risk_free_per_period="0", periods_per_year="1")
        )

    def test_experiment_id_is_convention_sensitive(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # Annualization is folded into identity (locked D5).
        corpus = populate(tmp_path)
        spec = ExperimentSpecification(
            name="e", base=base_spec(corpus), axes=(select_n_axis(),)
        )
        assert spec.experiment_id(
            risk_free_per_period="0", periods_per_year="1"
        ) != spec.experiment_id(risk_free_per_period="0", periods_per_year="12")

    def test_experiment_id_is_axis_sensitive(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        base = base_spec(corpus)
        a = ExperimentSpecification(name="e", base=base, axes=(select_n_axis(1, 2),))
        b = ExperimentSpecification(name="e", base=base, axes=(select_n_axis(1, 3),))
        assert a.experiment_id(risk_free_per_period="0", periods_per_year="1") != (
            b.experiment_id(risk_free_per_period="0", periods_per_year="1")
        )


class TestExpansion:
    def test_expansion_is_deterministic(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        spec = ExperimentSpecification(
            name="e", base=base_spec(corpus), axes=(select_n_axis(1, 2),)
        )
        first = [coord for coord, _ in spec.expand()]
        second = [coord for coord, _ in spec.expand()]
        assert first == second

    def test_single_axis_family_size(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        spec = ExperimentSpecification(
            name="e", base=base_spec(corpus), axes=(select_n_axis(1, 2),)
        )
        family = spec.expand()
        assert len(family) == 2
        # Each child differs only in select_n; both inherit the base corpus pins.
        assert {child.strategy.select_n for _, child in family} == {1, 2}

    def test_cartesian_product_size(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        spec = ExperimentSpecification(
            name="e",
            base=base_spec(corpus),
            axes=(
                select_n_axis(1, 2),
                SweepAxis("rank", ("descending", "ascending")),
            ),
        )
        family = spec.expand()
        assert len(family) == 4
        combos = {
            (child.strategy.select_n, child.strategy.rank_direction)
            for _, child in family
        }
        assert combos == {
            (1, "descending"),
            (1, "ascending"),
            (2, "descending"),
            (2, "ascending"),
        }

    def test_expansion_is_axis_declaration_order_independent(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        base = base_spec(corpus)
        rank_axis = SweepAxis("rank", ("descending", "ascending"))
        a = ExperimentSpecification(
            name="e", base=base, axes=(select_n_axis(1, 2), rank_axis)
        )
        b = ExperimentSpecification(
            name="e", base=base, axes=(rank_axis, select_n_axis(1, 2))
        )
        assert [c for c, _ in a.expand()] == [c for c, _ in b.expand()]

    def test_children_inherit_corpus_pins_verbatim(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # Locked D2: corpus pins are inherited, never swept.
        corpus = populate(tmp_path)
        base = base_spec(corpus)
        spec = ExperimentSpecification(name="e", base=base, axes=(select_n_axis(1, 2),))
        for _, child in spec.expand():
            assert child.dataset_version_id == base.dataset_version_id
            assert child.market_dataset_version_id == base.market_dataset_version_id

    def test_cost_axis_rebuilds_only_cost_model(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        corpus = populate(tmp_path)
        base = base_spec(corpus, cost_model=CostModel(proportional_bps="10"))
        spec = ExperimentSpecification(
            name="e",
            base=base,
            axes=(SweepAxis("cost_model.proportional_bps", ("0", "25")),),
        )
        family = dict(spec.expand())
        bps = {child.cost_model.proportional_bps for child in family.values()}
        assert bps == {"0", "25"}
        # The fixed leg is inherited from the base cost model (default "0").
        for child in family.values():
            assert child.cost_model.fixed_per_order == base.cost_model.fixed_per_order

    def test_schedule_axis_rebuilds_schedule(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from tests.backtest.builders import default_schedule

        corpus = populate(tmp_path)
        spec = ExperimentSpecification(
            name="e",
            base=base_spec(corpus),
            axes=(SweepAxis("schedule", (default_schedule(), alt_schedule())),),
        )
        family = [child for _, child in spec.expand()]
        assert {child.schedule.schedule_id for child in family} == {
            default_schedule().schedule_id,
            alt_schedule().schedule_id,
        }
