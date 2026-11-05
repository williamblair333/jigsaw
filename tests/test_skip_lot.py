"""skip-lot-gate (STANDARDS idea): after an agreement streak, escalate a kind less often;
one disagreement snaps it back to always (ANSI/ASQ Z1.4 switching rules)."""

from pathlib import Path
import random

from jigsaw.decision_log import DecisionLog, Option
from jigsaw.ladder import Gate, GateConfig, Ladder, Request, Verdict
from jigsaw.replay import replay_gate
from jigsaw.skip_lot import SkipLotGate


class Cheap:
    rung = 2

    def __init__(self, choice: str = "spears") -> None:
        self.choice = choice

    def decide(self, req: Request) -> Verdict | None:
        return Verdict(choice=self.choice, rung=2, reason="rule")


class Model:
    rung = 7

    def __init__(self, choice: str = "spears") -> None:
        self.choice = choice
        self.calls = 0

    def decide(self, req: Request) -> Verdict | None:
        self.calls += 1
        return Verdict(choice=self.choice, rung=7, reason="model")


def _close(turn: int, kind: str = "recruit", **kw) -> Request:
    """A close call (0.55 vs 0.5), so the base gate escalates."""
    return Request(game="g", turn=turn, actor="a", kind=kind, situation="s",
                   options=[Option(name="spears", score=0.55), Option(name="archers", score=0.5)], **kw)


def _gate(streak: int = 3, sample: float = 0.0) -> SkipLotGate:
    return SkipLotGate(GateConfig(cadence=0), streak=streak, sample=sample, rng=random.Random(1))


def test_escalates_normally_until_the_streak() -> None:
    model = Model()
    ladder = Ladder([Cheap(), model], _gate(streak=3))
    rungs = [ladder.decide(_close(t)).rung for t in range(1, 6)]
    assert rungs == [7, 7, 7, 2, 2]          # 3 agreements, then skipped (sample=0)
    assert model.calls == 3


def test_one_disagreement_snaps_back_to_always() -> None:
    gate = _gate(streak=2)
    for _ in range(2):
        gate.observe(_close(0), True, "close call (0.55 vs 0.50)")
    assert gate.check(_close(1), Verdict(choice="spears", rung=2, reason="r")) == ""
    gate.observe(_close(0), False, "close call (0.55 vs 0.50)")
    assert gate.check(_close(2), Verdict(choice="spears", rung=2, reason="r")).startswith("close call")


def test_streaks_are_per_kind() -> None:
    gate = _gate(streak=1)
    gate.observe(_close(0), True, "close call (0.55 vs 0.50)")
    v = Verdict(choice="x", rung=2, reason="r")
    assert gate.check(_close(1, kind="recruit"), v) == ""
    assert gate.check(_close(1, kind="build"), v).startswith("close call")


def test_sample_still_audits_some_skips() -> None:
    gate = SkipLotGate(GateConfig(cadence=0), streak=1, sample=0.5, rng=random.Random(7))
    gate.observe(_close(0), True, "close call (0.55 vs 0.50)")
    v = Verdict(choice="x", rung=2, reason="r")
    reasons = [gate.check(_close(t), v) for t in range(200)]
    audited = sum(1 for r in reasons if r)
    assert 70 < audited < 130                 # about half
    assert all(r.endswith("(skip-lot sample)") for r in reasons if r)
    assert gate.skipped[("g", "recruit")] == 200 - audited


def test_high_stakes_and_human_are_never_skipped() -> None:
    gate = _gate(streak=1)
    gate.observe(_close(0), True, "close call (0.55 vs 0.50)")
    v = Verdict(choice="x", rung=2, reason="r")
    assert gate.check(_close(1, stakes=0.9), v).startswith("high stakes")
    assert gate.check(_close(1, human=True), v) == "human involved"


def test_novelty_is_never_skipped() -> None:
    gate = _gate(streak=1)
    gate.observe(_close(0), True, "close call (0.55 vs 0.50)")
    assert gate.check(_close(1), None).startswith("novelty")


def test_ladder_reports_disagreement_too() -> None:
    gate = _gate(streak=2)
    ladder = Ladder([Cheap("spears"), Model("archers")], gate)
    for t in range(1, 6):
        assert ladder.decide(_close(t)).rung == 7   # never agrees, so never skips
    assert gate.streak("g", "recruit") == 0


def test_plain_gate_is_unchanged() -> None:
    ladder = Ladder([Cheap(), Model()], Gate(GateConfig(cadence=0)))
    assert [ladder.decide(_close(t)).rung for t in range(1, 6)] == [7] * 5


def test_cli_replays_through_skip_lot(tmp_path: Path, capsys) -> None:
    from jigsaw.cli import main

    log = DecisionLog(tmp_path / "d.db")
    ladder = Ladder([Cheap(), Model()], Gate(GateConfig(cadence=0)), log)
    for t in range(1, 11):
        ladder.decide(_close(t))
    log.close()

    rc = main(["replay", str(tmp_path / "d.db"), "--gate", "cadence=0", "--skip-lot", "streak=3,sample=0"])

    out = capsys.readouterr().out
    assert rc == 0 and "escalated: 10 logged, 3 now" in out and "choice would change: 0" in out


def test_cli_skip_lot_needs_gate(tmp_path: Path, capsys) -> None:
    from jigsaw.cli import main

    DecisionLog(tmp_path / "d.db").close()
    rc = main(["replay", str(tmp_path / "d.db"), "--ladder", "x:y", "--skip-lot", "streak=3"])
    assert rc == 2


def test_replay_runs_the_idea_test_offline(tmp_path: Path) -> None:
    """Log a campaign with the plain gate, then replay it through a skip-lot gate."""
    log = DecisionLog(tmp_path / "d.db")
    ladder = Ladder([Cheap(), Model()], Gate(GateConfig(cadence=0)), log)
    for t in range(1, 11):
        ladder.decide(_close(t))

    report = replay_gate(log, _gate(streak=3))

    assert report.escalated_before == 10
    assert report.escalated_now == 3            # the first three build the streak
    assert report.changed_choices == 0          # the model always agreed: no misses


def test_high_stakes_agreements_do_not_build_a_streak() -> None:
    gate = _gate(streak=2)
    model = Model()
    ladder = Ladder([Cheap(), model], gate)
    for t in range(1, 6):
        ladder.decide(_close(t, stakes=0.9))     # escalated as high stakes, model agrees
    assert gate.streak("g", "recruit") == 0
    assert ladder.decide(_close(6)).rung == 7      # the routine close call is still asked


def test_streaks_are_per_game() -> None:
    gate = _gate(streak=1)
    gate.observe(_close(0), True, "close call (0.55 vs 0.50)")   # game "g"
    other = _close(1).model_copy(update={"game": "h"})
    v = Verdict(choice="x", rung=2, reason="r")
    assert gate.check(_close(1), v) == ""
    assert gate.check(other, v).startswith("close call")
