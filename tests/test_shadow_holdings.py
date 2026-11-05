"""Two STANDARDS ideas: shadow-audit-sample and holdings-for-distillation (schema 5)."""

from pathlib import Path
import random
import sqlite3
from typing import Any

import pytest

from jigsaw.cli import main
from jigsaw.decision_log import SCHEMA_VERSION, DecisionLog, Option
from jigsaw.distill import Holding, HoldingsDecider, evaluate_holdings, holdings
from jigsaw.ladder import Gate, GateConfig, Ladder, Request, Verdict
from jigsaw.report import concordance


class Cheap:
    rung = 2

    def decide(self, req: Request) -> Verdict | None:
        return Verdict(choice="spears", rung=2, reason="rule")


class Model:
    rung = 7

    def __init__(self, choice: str = "archers", holding: dict[str, Any] | None = None) -> None:
        self.choice = choice
        self.holding = holding
        self.calls = 0

    def decide(self, req: Request) -> Verdict | None:
        self.calls += 1
        return Verdict(choice=self.choice, rung=7, reason="model", holding=self.holding)


def _quiet(turn: int, **context: Any) -> Request:
    return Request(game="g", turn=turn, actor="a", kind="recruit", situation="s",
                   options=[Option(name="spears", score=0.9), Option(name="archers", score=0.1)],
                   context=context)


QUIET = GateConfig(cadence=0)

# ---------------------------------------------------------------------------
# shadow audit
# ---------------------------------------------------------------------------


def test_shadow_off_by_default(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    model = Model()
    v = Ladder([Cheap(), model], Gate(QUIET), log).decide(_quiet(1))
    assert model.calls == 0 and v.shadow_choice is None
    assert log.get(v.decision_id).shadow_choice is None


def test_shadow_asks_the_strong_rung_but_does_not_act(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    model = Model("archers")
    v = Ladder([Cheap(), model], Gate(QUIET), log, shadow_rate=1.0,
               shadow_rng=random.Random(0)).decide(_quiet(1))

    assert (v.choice, v.rung, v.escalated_because) == ("spears", 2, "")   # the cheap answer stands
    assert (v.shadow_choice, v.shadow_rung) == ("archers", 7)
    row = log.get(v.decision_id)
    assert (row.shadow_choice, row.shadow_rung) == ("archers", 7)


def test_shadow_rate_samples(tmp_path: Path) -> None:
    model = Model()
    ladder = Ladder([Cheap(), model], Gate(QUIET), shadow_rate=0.1, shadow_rng=random.Random(3))
    for t in range(500):
        ladder.decide(_quiet(t))
    assert 25 < model.calls < 80


def test_shadow_never_runs_on_escalated_decisions() -> None:
    model = Model()
    ladder = Ladder([Cheap(), model], Gate(), shadow_rate=1.0, shadow_rng=random.Random(0))
    v = ladder.decide(_quiet(1).model_copy(update={"stakes": 0.9}))
    assert v.rung == 7 and model.calls == 1 and v.shadow_choice is None


def test_shadow_failure_is_contained() -> None:
    class Broken:
        rung = 7

        def decide(self, req: Request) -> Verdict | None:
            raise ConnectionError("model down")

    v = Ladder([Cheap(), Broken()], Gate(QUIET), shadow_rate=1.0,
               shadow_rng=random.Random(0)).decide(_quiet(1))
    assert v.choice == "spears" and v.shadow_choice is None and v.decider_errors == []


def test_concordance_reports_shadow_agreement(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    Ladder([Cheap(), Model("spears")], Gate(QUIET), log, shadow_rate=1.0,
           shadow_rng=random.Random(0)).decide(_quiet(1))
    Ladder([Cheap(), Model("archers")], Gate(QUIET), log, shadow_rate=1.0,
           shadow_rng=random.Random(0)).decide(_quiet(2))
    (row,) = concordance(log)
    assert (row.shadowed, row.shadow_agreed) == (2, 1)
    assert row.shadow_agreement == pytest.approx(0.5)


def test_shadow_rate_out_of_range_is_refused() -> None:
    with pytest.raises(ValueError):
        Ladder([Cheap()], Gate(), shadow_rate=1.5)


# ---------------------------------------------------------------------------
# holdings
# ---------------------------------------------------------------------------

POOR = {"when": {"treasury": {"max": 500}}, "choose": "spears"}


def _escalated(turn: int, **context: Any) -> Request:
    return _quiet(turn, **context).model_copy(update={"stakes": 0.9})


def test_model_holding_is_logged(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    v = Ladder([Cheap(), Model("spears", POOR)], Gate(), log).decide(_escalated(1, treasury=200))
    assert v.holding == Holding(when={"treasury": {"max": 500}}, choose="spears", kind="recruit")
    assert log.get(v.decision_id).holding == POOR


def test_holding_must_choose_its_own_answer() -> None:
    v = Ladder([Cheap(), Model("archers", POOR)], Gate()).decide(_escalated(1, treasury=200))
    assert v.holding is None and "holding chooses 'spears' but the answer is 'archers'" in v.reason


def test_holding_matching() -> None:
    h = Holding(when={"treasury": {"min": 100, "max": 500}, "season": ["winter", "autumn"],
                      "at_war": True}, choose="spears")
    assert h.matches({"treasury": 300, "season": "winter", "at_war": True})
    assert not h.matches({"treasury": 600, "season": "winter", "at_war": True})
    assert not h.matches({"treasury": 300, "season": "summer", "at_war": True})
    assert not h.matches({"treasury": 300, "season": "winter"})              # missing key
    assert not h.matches({"treasury": "lots", "season": "winter", "at_war": True})


def test_holdings_decider_applies_matching_holdings_at_rung_1() -> None:
    d = HoldingsDecider([Holding(kind="recruit", when={"treasury": {"max": 500}}, choose="spears",
                                 source_id=7)])
    v = d.decide(_quiet(1, treasury=200))
    assert v is not None and (v.choice, v.rung) == ("spears", 1)
    assert "holding from decision #7" in v.reason
    assert d.decide(_quiet(1, treasury=900)) is None
    assert d.decide(_quiet(1, treasury=200).model_copy(update={"kind": "build"})) is None


def test_holding_whose_choice_is_not_an_option_passes() -> None:
    d = HoldingsDecider([Holding(kind="recruit", when={}, choose="knights")])
    assert d.decide(_quiet(1)) is None


def test_holdings_are_read_from_the_log_with_provenance(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    v = Ladder([Cheap(), Model("spears", POOR)], Gate(), log).decide(_escalated(1, treasury=200))
    (h,) = holdings(log)
    assert (h.kind, h.choose, h.source_id) == ("recruit", "spears", v.decision_id)


def test_evaluate_holdings_counts_matches_and_agreement(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    Ladder([Cheap(), Model("spears", POOR)], Gate(), log).decide(_escalated(1, treasury=200))
    plain = Ladder([Cheap(), Model("archers")], Gate(), log)
    plain.decide(_escalated(2, treasury=300))      # matches, but the model chose archers
    plain.decide(_escalated(3, treasury=900))      # doesn't match
    Ladder([Cheap(), Model("spears")], Gate(), log).decide(_escalated(4, treasury=100))  # agrees

    (ev,) = evaluate_holdings(log)
    assert (ev.matched, ev.agreed) == (3, 2)          # turns 1, 2, 4 match; 1 and 4 agree
    assert ev.agreement == pytest.approx(2 / 3)


def test_cli_holdings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = DecisionLog(tmp_path / "d.db")
    Ladder([Cheap(), Model("spears", POOR)], Gate(), log).decide(_escalated(1, treasury=200))
    log.close()
    assert main(["holdings", str(tmp_path / "d.db")]) == 0
    out = capsys.readouterr().out
    assert "recruit" in out and "spears" in out and "100%" in out


# ---------------------------------------------------------------------------
# schema 5
# ---------------------------------------------------------------------------


def test_schema_5_migrates_a_v4_file(tmp_path: Path) -> None:
    path = tmp_path / "v4.db"
    DecisionLog(path).close()
    with sqlite3.connect(path) as conn:
        for col in ("shadow_choice", "shadow_rung", "holding"):
            conn.execute(f"ALTER TABLE decisions DROP COLUMN {col}")
        conn.execute("PRAGMA user_version = 4")
    DecisionLog(path).close()
    with sqlite3.connect(path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(decisions)")}
        assert {"shadow_choice", "shadow_rung", "holding"} <= cols
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 5
