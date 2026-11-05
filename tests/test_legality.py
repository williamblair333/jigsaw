"""The pack's legality check runs on every verdict; an illegal verdict passes up instead of being sent."""

from pathlib import Path

from jigsaw.decision_log import DecisionLog
from jigsaw.ladder import Gate, GateConfig, Ladder, Request, Verdict


class Answers:
    def __init__(self, rung: int, choice: str) -> None:
        self.rung = rung
        self.choice = choice

    def decide(self, req: Request) -> Verdict | None:
        return Verdict(choice=self.choice, rung=self.rung, reason="ok",
                       primitives=[{"move": self.choice}])


def no_archers(req: Request, v: Verdict) -> str | None:
    return "no archery range in this town" if v.choice == "archers" else None


def _req(**kw) -> Request:
    return Request(game="g", turn=3, actor="a", kind="recruit", situation="s", **kw)


def test_illegal_model_verdict_passes_up_and_the_cheap_answer_stands(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    ladder = Ladder([Answers(2, "spears"), Answers(7, "archers")], Gate(), log, legality=no_archers)

    v = ladder.decide(_req(stakes=0.9))

    assert (v.choice, v.rung) == ("spears", 2)
    assert "rung 7 illegal (no archery range in this town)" in v.reason
    assert v.legality == [
        {"rung": 2, "choice": "spears", "legal": True},
        {"rung": 7, "choice": "archers", "legal": False, "reason": "no archery range in this town"},
    ]
    assert log.get(v.decision_id).legality == v.legality


def test_illegal_cheap_verdict_passes_to_the_next_cheap_rung() -> None:
    ladder = Ladder([Answers(1, "archers"), Answers(2, "spears")], Gate(GateConfig(cadence=0)),
                    legality=no_archers)

    v = ladder.decide(_req())

    assert (v.choice, v.rung) == ("spears", 2)
    assert [e["legal"] for e in v.legality] == [False, True]


def test_illegal_only_cheap_answer_escalates_as_novelty() -> None:
    ladder = Ladder([Answers(2, "archers"), Answers(7, "spears")], Gate(GateConfig(cadence=0)),
                    legality=no_archers)

    v = ladder.decide(_req())

    assert (v.choice, v.rung) == ("spears", 7)
    assert v.escalated_because.startswith("novelty")


def test_every_answer_illegal_leaves_it_to_the_game() -> None:
    ladder = Ladder([Answers(2, "archers"), Answers(7, "archers")], Gate(), legality=no_archers)

    v = ladder.decide(_req())

    assert (v.choice, v.rung) == ("", 0)
    assert [e["legal"] for e in v.legality] == [False, False]


def test_a_check_that_raises_refuses_the_verdict() -> None:
    def broken(req: Request, v: Verdict) -> str | None:
        raise KeyError("settlement 42")

    ladder = Ladder([Answers(2, "spears")], Gate(GateConfig(cadence=0)), legality=broken)

    v = ladder.decide(_req())

    assert (v.choice, v.rung) == ("", 0)
    assert v.legality == [{"rung": 2, "choice": "spears", "legal": False,
                           "reason": "legality check raised KeyError: 'settlement 42'"}]


def test_no_check_means_no_legality_entries(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    v = Ladder([Answers(2, "spears")], Gate(GateConfig(cadence=0)), log).decide(_req())
    assert v.legality == [] and log.get(v.decision_id).legality == []
