"""A rung asked after a failure sees what failed below it (spec §5: escalate with the trace)."""

from pathlib import Path
from typing import Any

from jigsaw.decision_log import DecisionLog
from jigsaw.intent import Intent
from jigsaw.ladder import Gate, GateConfig, Ladder, Request, Verdict


class Records:
    """Answers with a fixed verdict (or None) and keeps every request it was given."""

    def __init__(self, rung: int, verdict: Verdict | None) -> None:
        self.rung = rung
        self.verdict = verdict
        self.seen: list[Request] = []

    def decide(self, req: Request) -> Verdict | None:
        self.seen.append(req)
        return self.verdict


class Raises:
    rung = 1

    def decide(self, req: Request) -> Verdict | None:
        raise ValueError("bad table")


def _req(**kw: Any) -> Request:
    return Request(game="g", turn=3, actor="a", kind="k", situation="s", **kw)


def test_first_rung_sees_an_empty_trace() -> None:
    first = Records(2, Verdict(choice="x", rung=2, reason="ok"))
    Ladder([first], Gate(GateConfig(cadence=0))).decide(_req())
    assert first.seen[0].trace == []


def test_next_rung_sees_the_error_below_it() -> None:
    nxt = Records(2, Verdict(choice="x", rung=2, reason="ok"))
    Ladder([Raises(), nxt], Gate(GateConfig(cadence=0))).decide(_req())
    assert nxt.seen[0].trace == [{"rung": 1, "error": "ValueError: bad table"}]


def test_model_rung_sees_the_cheap_refusal() -> None:
    cheap = Records(2, Verdict(choice="archers", rung=2, reason="rule"))
    model = Records(7, Verdict(choice="spears", rung=7, reason="model"))

    def no_archers(req: Request, v: Verdict) -> str | None:
        return "no range" if v.choice == "archers" else None

    v = Ladder([cheap, model], Gate(GateConfig(cadence=0)), legality=no_archers).decide(_req())

    assert v.choice == "spears"
    assert model.seen[0].trace == [{"rung": 2, "choice": "archers", "legal": False, "reason": "no range"}]


def test_failed_intent_attempts_reach_the_next_model_rung() -> None:
    class NoPlan:
        def expand(self, req: Request, intent: Intent, failure: str | None) -> list[dict[str, Any]] | None:
            return None

    take = Verdict(choice="take Milan", rung=6, reason="model", intent=Intent(verb="take"))
    hold = Verdict(choice="hold", rung=7, reason="model", intent=Intent(verb="hold"))

    class Hold:
        def expand(self, req: Request, intent: Intent, failure: str | None) -> list[dict[str, Any]] | None:
            return [{"op": "wait"}]

    strong = Records(7, hold)
    v = Ladder([Records(6, take), strong], Gate(),
               expanders={"take": NoPlan(), "hold": Hold()}).decide(_req(stakes=0.9))

    assert v.rung == 7
    reasons = [t.get("reason") for t in strong.seen[0].trace]
    assert reasons == ["the expander found no plan", "the expander found no plan",
                       "intent take failed after replanning: the expander found no plan"]


def test_caller_trace_is_kept_first_and_logged_as_given(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    nxt = Records(2, Verdict(choice="x", rung=2, reason="ok"))
    game_failure = {"source": "game", "error": "march blocked at Verona"}

    v = Ladder([Raises(), nxt], Gate(GateConfig(cadence=0)), log).decide(_req(trace=[game_failure]))

    assert nxt.seen[0].trace == [game_failure, {"rung": 1, "error": "ValueError: bad table"}]
    assert log.get(v.decision_id).request["trace"] == [game_failure]


def test_callers_request_is_not_mutated() -> None:
    req = _req()
    Ladder([Raises(), Records(2, Verdict(choice="x", rung=2, reason="ok"))],
           Gate(GateConfig(cadence=0))).decide(req)
    assert req.trace == []


def test_old_logged_request_without_trace_still_validates() -> None:
    old = {"game": "g", "turn": 1, "actor": "a", "kind": "k", "situation": "s", "options": [],
           "stakes": 0.0, "human": False, "context": {}}
    assert Request.model_validate(old).trace == []
