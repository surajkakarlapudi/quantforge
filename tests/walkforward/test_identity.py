"""Content-addressed identity of the walk-forward layer (§13, §11)."""

from __future__ import annotations

from quantforge.walkforward.identity import walk_forward_id, walk_forward_result_hash


def _id(**overrides: object) -> str:
    kwargs: dict[str, object] = {
        "walk_forward_engine_version_id": "sha256:engine",
        "name": "w",
        "spec_version": "walkforward/1",
        "training_policy": {"window": "expanding", "min_train_periods": 3},
        "schedule_id": "sched",
        "optimization_id": "sha256:opt",
        "optimization_result_hash": "sha256:opthash",
        "result_hash": "sha256:rhash",
    }
    kwargs.update(overrides)
    return walk_forward_id(**kwargs)  # type: ignore[arg-type]


class TestResultHash:
    def test_sha256_prefixed(self) -> None:
        assert walk_forward_result_hash([{"block": "oos", "returns": []}]).startswith(
            "sha256:"
        )

    def test_deterministic(self) -> None:
        cells: list[dict[str, object]] = [{"block": "oos", "returns": ["0.1"]}]
        assert walk_forward_result_hash(cells) == walk_forward_result_hash(cells)

    def test_sensitive_to_a_single_cell(self) -> None:
        base = walk_forward_result_hash([{"block": "oos", "returns": ["0.1"]}])
        other = walk_forward_result_hash([{"block": "oos", "returns": ["0.2"]}])
        assert base != other

    def test_sensitive_to_cell_order(self) -> None:
        a = walk_forward_result_hash(
            [{"block": "window", "index": 0}, {"block": "window", "index": 1}]
        )
        b = walk_forward_result_hash(
            [{"block": "window", "index": 1}, {"block": "window", "index": 0}]
        )
        assert a != b


class TestWalkForwardId:
    def test_sha256_prefixed_and_deterministic(self) -> None:
        assert _id().startswith("sha256:")
        assert _id() == _id()

    def test_sensitive_to_every_fold(self) -> None:
        base = _id()
        assert _id(walk_forward_engine_version_id="sha256:other") != base
        assert _id(name="other") != base
        assert _id(spec_version="walkforward/2") != base
        assert (
            _id(training_policy={"window": "rolling", "min_train_periods": 3}) != base
        )
        assert _id(schedule_id="other") != base
        assert _id(optimization_id="sha256:other") != base
        assert _id(optimization_result_hash="sha256:other") != base
        assert _id(result_hash="sha256:other") != base

    def test_training_policy_folded_as_canonical_json_not_key_order(self) -> None:
        a = _id(training_policy={"window": "expanding", "min_train_periods": 3})
        b = _id(training_policy={"min_train_periods": 3, "window": "expanding"})
        assert a == b
