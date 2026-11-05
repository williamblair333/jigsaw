"""Model rungs answer with intents; the pack's expanders turn them into primitives (spec §5)."""

from pathlib import Path
import sqlite3
from typing import Any

from jigsaw.decision_log import SCHEMA_VERSION, DecisionLog
from jigsaw.intent import Intent
from jigsaw.ladder import Gate, GateConfig, Ladder, Request, Verdict


class Cheap:
    rung = 2

    def decide(self, req: Request) -> Verdict | None:
        return Verdict(choice="hold", rung=2, reason="rule", primitives=[{"op": "wait"}])


class Model:
    """Rung 7: answers with whatever verdict it was built with."""

    rung = 7

    def __init__(self, verdict: Verdict) -> None:
        self.verdict = verdict

    def decide(self, req: Request) -> Verdict | None:
        return self.verdict


def _take(target: str = "Milan") -> Verdict:
    return Verdict(choice=f"take {target}", rung=7, reason="model",
                   intent=Intent(verb="take", args={"target": target, "general": "Doge Enrico"}))


class TakeExpander:
    """Plans a march; the first plan uses the road named in `bad_road` when given."""

    def __init__(self, bad_road: str | None = None, always_none: bool = False) -> None:
        self.bad_road = bad_road
        self.always_none = always_none
        self.calls: list[str | None] = []

    def expand(self, req: Request, intent: Intent, failure: str | None) -> list[dict[str, Any]] | None:
        self.calls.append(failure)
        if self.always_none:
            return None
        road = self.bad_road if (failure is None and self.bad_road) else "coast road"
        return [{"op": "march", "via": road, "to": intent.args["target"]},
                {"op": "siege", "at": intent.args["target"]}]


def no_mountain_pass(req: Request, v: Verdict) -> str | None:
    if any(p.get("via") == "mountain pass" for p in v.primitives):
        return "mountain pass is snowed in"
    return None


def _req(**kw: Any) -> Request:
    return Request(game="g", turn=3, actor="venice", kind="war", situation="s", stakes=0.9, **kw)


def test_intent_is_expanded_into_primitives(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    ladder = Ladder([Cheap(), Model(_take())], Gate(), log, expanders={"take": TakeExpander()})

    v = ladder.decide(_req())

    assert (v.choice, v.rung) == ("take Milan", 7)
    assert v.intent is not None and v.intent.verb == "take"
    assert v.primitives == [{"op": "march", "via": "coast road", "to": "Milan"},
                            {"op": "siege", "at": "Milan"}]
    row = log.get(v.decision_id)
    assert row.intent == v.intent.model_dump()
    assert row.primitives == v.primitives


def test_refused_plan_is_replanned_once_with_the_reason(tmp_path: Path) -> None:
    exp = TakeExpander(bad_road="mountain pass")
    ladder = Ladder([Cheap(), Model(_take())], Gate(), expanders={"take": exp},
                    legality=no_mountain_pass)

    v = ladder.decide(_req())

    assert exp.calls == [None, "mountain pass is snowed in"]
    assert v.rung == 7 and v.primitives[0]["via"] == "coast road"
    assert [c["legal"] for c in v.legality] == [True, False, True]   # cheap, plan 1, plan 2
    assert v.legality[2]["attempt"] == 2 and v.legality[2]["intent_id"] == v.intent.id


def test_intent_that_fails_twice_passes_up_and_the_cheap_answer_stands() -> None:
    exp = TakeExpander(always_none=True)
    ladder = Ladder([Cheap(), Model(_take())], Gate(), expanders={"take": exp})

    v = ladder.decide(_req())

    assert (v.choice, v.rung) == ("hold", 2)
    assert len(exp.calls) == 2
    assert "rung 7 illegal (intent take failed after replanning: the expander found no plan)" in v.reason


def test_unknown_verb_is_refused() -> None:
    bribe = Verdict(choice="bribe Milan", rung=7, reason="model", intent=Intent(verb="bribe"))
    ladder = Ladder([Cheap(), Model(bribe)], Gate(), expanders={"take": TakeExpander()})

    v = ladder.decide(_req())

    assert v.rung == 2
    assert "no expander for intent verb 'bribe'" in v.reason


def test_model_rung_emitting_primitives_is_refused_when_expanders_are_set() -> None:
    raw = Verdict(choice="march", rung=7, reason="model", primitives=[{"op": "march", "army_id": 4471}])
    ladder = Ladder([Cheap(), Model(raw)], Gate(), expanders={"take": TakeExpander()})

    v = ladder.decide(_req())

    assert v.rung == 2
    assert "model rungs answer with an intent, not primitives" in v.reason


def test_cheap_rungs_may_still_emit_primitives() -> None:
    ladder = Ladder([Cheap()], Gate(GateConfig(cadence=0)), expanders={"take": TakeExpander()})
    v = ladder.decide(Request(game="g", turn=3, actor="a", kind="k", situation="s"))
    assert (v.rung, v.primitives) == (2, [{"op": "wait"}])


def test_without_expanders_nothing_changes() -> None:
    raw = Verdict(choice="march", rung=7, reason="model", primitives=[{"op": "march"}])
    v = Ladder([Cheap(), Model(raw)], Gate()).decide(_req())
    assert (v.rung, v.primitives) == (7, [{"op": "march"}])


def test_expander_that_raises_counts_as_a_failed_plan() -> None:
    class Broken:
        def expand(self, req: Request, intent: Intent, failure: str | None) -> list[dict[str, Any]] | None:
            raise KeyError("Milan")

    v = Ladder([Cheap(), Model(_take())], Gate(), expanders={"take": Broken()}).decide(_req())

    assert v.rung == 2
    assert "expander raised KeyError: 'Milan'" in v.reason


def test_schema_4_adds_the_intent_column_to_a_v3_file(tmp_path: Path) -> None:
    path = tmp_path / "v3.db"
    DecisionLog(path).close()
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE decisions DROP COLUMN intent")
        conn.execute("PRAGMA user_version = 3")
    DecisionLog(path).close()
    with sqlite3.connect(path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(decisions)")]
        assert "intent" in cols
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 4
