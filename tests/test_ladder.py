"""Tests for Jigsaw decision ladder and gate."""

from pathlib import Path
import pytest

from jigsaw.decision_log import DecisionLog, Option
from jigsaw.ladder import (
    Decider,
    Gate,
    GateConfig,
    Ladder,
    Request,
    Verdict,
    normalise,
)


class FakeDecider:
    """Fake decider for ladder tests."""

    def __init__(self, rung: int, verdict: Verdict | None = None) -> None:
        self.rung = rung
        self.verdict = verdict
        self.called_with: list[Request] = []

    def decide(self, req: Request) -> Verdict | None:
        self.called_with.append(req)
        return self.verdict


# ---------------------------------------------------------------------------
# normalise edge cases
# ---------------------------------------------------------------------------


def test_normalise_empty() -> None:
    assert normalise([]) == []


def test_normalise_all_none() -> None:
    opts = [
        Option(name="opt_a", score=None, note="first"),
        Option(name="opt_b", score=None, note="second"),
    ]
    norm = normalise(opts)
    assert len(norm) == 2
    assert norm[0].name == "opt_a"
    assert norm[0].score is None
    assert norm[0].note == "first"
    assert norm[1].name == "opt_b"
    assert norm[1].score is None
    assert norm[1].note == "second"


def test_normalise_single_scored() -> None:
    opts = [Option(name="only", score=42.0)]
    norm = normalise(opts)
    assert len(norm) == 1
    assert norm[0].score == 1.0


def test_normalise_all_equal() -> None:
    opts = [
        Option(name="a", score=5.0),
        Option(name="b", score=5.0),
        Option(name="c", score=None),
    ]
    norm = normalise(opts)
    assert norm[0].score == 1.0
    assert norm[1].score == 1.0
    assert norm[2].score is None


def test_normalise_min_max_spread() -> None:
    opts = [
        Option(name="low", score=10.0),
        Option(name="mid", score=20.0),
        Option(name="high", score=30.0),
        Option(name="unscored", score=None),
    ]
    norm = normalise(opts)
    assert norm[0].score == 0.0
    assert norm[1].score == 0.5
    assert norm[2].score == 1.0
    assert norm[3].score is None


def test_normalise_negative_scores() -> None:
    opts = [
        Option(name="neg", score=-10.0),
        Option(name="zero", score=0.0),
        Option(name="pos", score=10.0),
    ]
    norm = normalise(opts)
    assert norm[0].score == 0.0
    assert norm[1].score == 0.5
    assert norm[2].score == 1.0


# ---------------------------------------------------------------------------
# Gate reason checks and precedence order
# ---------------------------------------------------------------------------


def test_gate_human_precedence() -> None:
    gate = Gate(GateConfig(margin=0.2, stakes_threshold=0.5, cadence=5))
    # Human involved wins over stakes, novelty, close call, and cadence
    req = Request(
        game="test",
        turn=5,
        actor="p1",
        kind="test",
        situation="sit",
        options=[Option(name="a", score=1.0), Option(name="b", score=0.95)],
        stakes=0.9,
        human=True,
    )
    assert gate.check(req, verdict=None) == "human involved"


def test_gate_high_stakes_precedence() -> None:
    gate = Gate(GateConfig(margin=0.2, stakes_threshold=0.7, cadence=5))
    # High stakes wins over novelty, close call, and cadence
    req = Request(
        game="test",
        turn=5,
        actor="p1",
        kind="test",
        situation="sit",
        options=[Option(name="a", score=1.0), Option(name="b", score=0.95)],
        stakes=0.75,
        human=False,
    )
    assert gate.check(req, verdict=None) == "high stakes (0.75)"


def test_gate_novelty_precedence() -> None:
    gate = Gate(GateConfig(margin=0.2, stakes_threshold=0.7, cadence=5))
    # Novelty (verdict is None) wins over close call and cadence
    req = Request(
        game="test",
        turn=5,
        actor="p1",
        kind="test",
        situation="sit",
        options=[Option(name="a", score=1.0), Option(name="b", score=0.95)],
        stakes=0.3,
        human=False,
    )
    assert gate.check(req, verdict=None) == "novelty: no rule matched"


def test_gate_close_call_precedence() -> None:
    gate = Gate(GateConfig(margin=0.1, stakes_threshold=0.7, cadence=5))
    # Close call wins over cadence when verdict is present
    cheap_v = Verdict(choice="a", rung=1, reason="cheap")
    req = Request(
        game="test",
        turn=5,
        actor="p1",
        kind="test",
        situation="sit",
        options=[
            Option(name="a", score=100.0),
            Option(name="b", score=98.0),
            Option(name="c", score=0.0),
        ],
        stakes=0.3,
        human=False,
    )
    assert gate.check(req, verdict=cheap_v) == "close call (1.00 vs 0.98)"


def test_gate_cadence_review() -> None:
    gate = Gate(GateConfig(margin=0.1, stakes_threshold=0.7, cadence=10))
    cheap_v = Verdict(choice="a", rung=1, reason="cheap")
    req = Request(
        game="test",
        turn=10,
        actor="p1",
        kind="test",
        situation="sit",
        options=[
            Option(name="a", score=100.0),
            Option(name="b", score=50.0),
            Option(name="c", score=0.0),
        ],
        stakes=0.3,
        human=False,
    )
    assert gate.check(req, verdict=cheap_v) == "cadence review (turn 10)"


def test_gate_no_escalation() -> None:
    gate = Gate(GateConfig(margin=0.1, stakes_threshold=0.7, cadence=10))
    cheap_v = Verdict(choice="a", rung=1, reason="cheap")
    req = Request(
        game="test",
        turn=7,
        actor="p1",
        kind="test",
        situation="sit",
        options=[
            Option(name="a", score=100.0),
            Option(name="b", score=50.0),
            Option(name="c", score=0.0),
        ],
        stakes=0.3,
        human=False,
    )
    assert gate.check(req, verdict=cheap_v) == ""


def test_gate_close_call_requires_two_scored_options() -> None:
    gate = Gate(GateConfig(margin=0.1))
    cheap_v = Verdict(choice="a", rung=1, reason="cheap")
    req = Request(
        game="test",
        turn=3,
        actor="p1",
        kind="test",
        situation="sit",
        options=[Option(name="a", score=10.0), Option(name="b", score=None)],
        stakes=0.2,
        human=False,
    )
    assert gate.check(req, verdict=cheap_v) == ""


def test_gate_cadence_zero_off() -> None:
    gate = Gate(GateConfig(cadence=0))
    cheap_v = Verdict(choice="a", rung=1, reason="cheap")
    req = Request(
        game="test",
        turn=10,
        actor="p1",
        kind="test",
        situation="sit",
        options=[],
        stakes=0.1,
        human=False,
    )
    assert gate.check(req, verdict=cheap_v) == ""


def test_gate_turn_zero_no_cadence() -> None:
    gate = Gate(GateConfig(cadence=10))
    cheap_v = Verdict(choice="a", rung=1, reason="cheap")
    req = Request(
        game="test",
        turn=0,
        actor="p1",
        kind="test",
        situation="sit",
        options=[],
        stakes=0.1,
        human=False,
    )
    assert gate.check(req, verdict=cheap_v) == ""


# ---------------------------------------------------------------------------
# Ladder behavior tests
# ---------------------------------------------------------------------------


def test_no_escalation_keeps_cheap_verdict() -> None:
    cheap_verdict = Verdict(
        choice="build_farm",
        rung=1,
        reason="high utility",
        primitives=[{"action": "build", "target": "farm"}],
    )
    d1 = FakeDecider(rung=1, verdict=cheap_verdict)
    d5 = FakeDecider(rung=5, verdict=Verdict(choice="build_mine", rung=5, reason="llm"))
    gate = Gate(GateConfig(margin=0.1, stakes_threshold=0.7, cadence=10))
    ladder = Ladder(deciders=[d1, d5], gate=gate)

    req = Request(
        game="mtw2",
        turn=3,
        actor="england",
        kind="economy",
        situation="peace time",
        options=[Option(name="farm", score=10.0), Option(name="mine", score=2.0)],
        stakes=0.2,
        human=False,
    )

    verdict = ladder.decide(req)
    assert verdict == cheap_verdict
    assert verdict.reason == "high utility"
    assert len(d5.called_with) == 0  # Higher rung was not invoked


def test_escalation_hands_over_with_reason_prefixed() -> None:
    cheap_verdict = Verdict(choice="auto_tax", rung=2, reason="tax rule")
    higher_verdict = Verdict(
        choice="lower_tax",
        rung=6,
        reason="avoid rebellion",
        primitives=[{"action": "set_tax", "level": "low"}],
    )
    d2 = FakeDecider(rung=2, verdict=cheap_verdict)
    d6 = FakeDecider(rung=6, verdict=higher_verdict)
    gate = Gate(GateConfig(stakes_threshold=0.7))
    ladder = Ladder(deciders=[d2, d6], gate=gate)

    req = Request(
        game="mtw2",
        turn=4,
        actor="france",
        kind="economy",
        situation="public order critical",
        stakes=0.85,
        human=False,
    )

    verdict = ladder.decide(req)
    assert verdict.choice == "lower_tax"
    assert verdict.rung == 6
    assert verdict.reason == "high stakes (0.85); avoid rebellion"
    assert verdict.primitives == [{"action": "set_tax", "level": "low"}]


def test_escalation_with_no_higher_rung_keeps_cheap_verdict() -> None:
    cheap_verdict = Verdict(choice="charge", rung=2, reason="nearest enemy")
    d2 = FakeDecider(rung=2, verdict=cheap_verdict)
    # Decider at rung 6 returns None (cannot decide), no other higher deciders
    d6 = FakeDecider(rung=6, verdict=None)
    gate = Gate(GateConfig())
    ladder = Ladder(deciders=[d2, d6], gate=gate)

    req = Request(
        game="mtw2",
        turn=1,
        actor="spain",
        kind="tactics",
        situation="ambush",
        human=True,
    )

    verdict = ladder.decide(req)
    assert verdict.choice == "charge"
    assert verdict.rung == 2
    assert verdict.reason == "human involved (no higher rung available); nearest enemy"


def test_escalation_with_empty_higher_deciders_keeps_cheap_verdict() -> None:
    cheap_verdict = Verdict(choice="hold", rung=1, reason="default stance")
    d1 = FakeDecider(rung=1, verdict=cheap_verdict)
    gate = Gate(GateConfig())
    ladder = Ladder(deciders=[d1], gate=gate)

    req = Request(
        game="mtw2",
        turn=1,
        actor="scotland",
        kind="tactics",
        situation="defense",
        human=True,
    )

    verdict = ladder.decide(req)
    assert verdict.choice == "hold"
    assert verdict.rung == 1
    assert verdict.reason == "human involved (no higher rung available); default stance"


def test_rung_0_fallback_when_no_decider_answers() -> None:
    d1 = FakeDecider(rung=1, verdict=None)
    d6 = FakeDecider(rung=6, verdict=None)
    gate = Gate(GateConfig())
    ladder = Ladder(deciders=[d1, d6], gate=gate)

    req = Request(
        game="mtw2",
        turn=1,
        actor="holy_roman_empire",
        kind="strategy",
        situation="completely unknown scenario",
    )

    verdict = ladder.decide(req)
    assert verdict.choice == ""
    assert verdict.rung == 0
    assert verdict.reason == "no decider answered; the game's own AI keeps it"
    assert verdict.primitives == []


def test_none_from_cheap_decider_counts_as_novelty() -> None:
    d1 = FakeDecider(rung=1, verdict=None)
    d5 = FakeDecider(
        rung=5,
        verdict=Verdict(choice="parley", rung=5, reason="negotiate truce"),
    )
    gate = Gate(GateConfig())
    ladder = Ladder(deciders=[d1, d5], gate=gate)

    req = Request(
        game="mtw2",
        turn=2,
        actor="venice",
        kind="diplomacy",
        situation="unknown envoy arrived",
        human=False,
        stakes=0.1,
    )

    verdict = ladder.decide(req)
    assert verdict.choice == "parley"
    assert verdict.rung == 5
    assert verdict.reason == "novelty: no rule matched; negotiate truce"


def test_decider_ascending_rung_order() -> None:
    d1 = FakeDecider(rung=1, verdict=Verdict(choice="first", rung=1, reason="r1"))
    d2 = FakeDecider(rung=2, verdict=Verdict(choice="second", rung=2, reason="r2"))
    # Passed in reverse order: rung 2 before rung 1
    gate = Gate(GateConfig())
    ladder = Ladder(deciders=[d2, d1], gate=gate)

    req = Request(
        game="mtw2",
        turn=3,
        actor="venice",
        kind="diplomacy",
        situation="sit",
    )
    verdict = ladder.decide(req)
    assert verdict.choice == "first"
    assert verdict.rung == 1
    assert len(d2.called_with) == 0  # d1 answered first, so d2 was not reached


def test_higher_deciders_ascending_rung_order() -> None:
    d1 = FakeDecider(rung=1, verdict=Verdict(choice="cheap", rung=1, reason="r1"))
    d5 = FakeDecider(rung=5, verdict=Verdict(choice="mid", rung=5, reason="r5"))
    d7 = FakeDecider(rung=7, verdict=Verdict(choice="high", rung=7, reason="r7"))
    # Higher deciders passed in reverse order
    gate = Gate(GateConfig())
    ladder = Ladder(deciders=[d7, d1, d5], gate=gate)

    req = Request(
        game="mtw2",
        turn=3,
        actor="venice",
        kind="diplomacy",
        situation="sit",
        human=True,  # triggers escalation
    )
    verdict = ladder.decide(req)
    assert verdict.choice == "mid"
    assert verdict.rung == 5
    assert verdict.reason == "human involved; r5"
    assert len(d7.called_with) == 0  # d5 answered first, d7 not called


def test_decision_log_one_row_per_decide(tmp_path: Path) -> None:
    db_path = tmp_path / "decisions.db"
    log = DecisionLog(db_path)

    d1 = FakeDecider(
        rung=1,
        verdict=Verdict(
            choice="accept",
            rung=1,
            reason="cheap match",
            primitives=[{"p": 1}],
        ),
    )
    d6 = FakeDecider(
        rung=6,
        verdict=Verdict(
            choice="reject",
            rung=6,
            reason="counter offer",
            primitives=[{"p": 2}],
        ),
    )
    gate = Gate(GateConfig(margin=0.1, stakes_threshold=0.7, cadence=10))
    ladder = Ladder(deciders=[d1, d6], gate=gate, log=log)

    # 1. Unescalated call
    req_cheap = Request(
        game="mtw2",
        turn=3,
        actor="milan",
        kind="diplomacy",
        situation="ceasefire requested",
        options=[
            Option(name="accept", score=10.0),
            Option(name="reject", score=2.0),
        ],
        stakes=0.2,
        human=False,
    )
    ladder.decide(req_cheap)

    # 2. Escalated call (human)
    req_human = Request(
        game="mtw2",
        turn=4,
        actor="milan",
        kind="diplomacy",
        situation="human chat message",
        options=[Option(name="say_yes", score=1.0)],
        stakes=0.2,
        human=True,
    )
    ladder.decide(req_human)

    # 3. Novelty escalation where higher answers
    d_none = FakeDecider(rung=1, verdict=None)
    ladder_novelty = Ladder(deciders=[d_none, d6], gate=gate, log=log)
    req_novelty = Request(
        game="mtw2",
        turn=5,
        actor="milan",
        kind="diplomacy",
        situation="unmatched proposal",
        options=[],
        stakes=0.1,
    )
    ladder_novelty.decide(req_novelty)

    # Verify log records in database
    decisions = log.query(game="mtw2")
    assert len(decisions) == 3

    # Remember query() orders by id DESC, so decisions are [novelty, human, cheap]
    d_nov, d_hum, d_chp = decisions[0], decisions[1], decisions[2]

    # Verify unescalated decision
    assert d_chp.escalated_because == ""
    assert d_chp.choice == "accept"
    assert d_chp.rung == 1
    assert d_chp.primitives == [{"p": 1}]
    assert len(d_chp.options) == 2
    assert d_chp.options[0].name == "accept"
    assert d_chp.options[0].score == 1.0
    assert d_chp.options[1].name == "reject"
    assert d_chp.options[1].score == 0.0

    # Verify human escalated decision
    assert d_hum.escalated_because == "human involved"
    assert d_hum.choice == "reject"
    assert d_hum.rung == 6
    assert d_hum.primitives == [{"p": 2}]

    # Verify novelty escalated decision
    assert d_nov.escalated_because == "novelty: no rule matched"
    assert d_nov.choice == "reject"
    assert d_nov.rung == 6
    assert d_nov.primitives == [{"p": 2}]

    log.close()
