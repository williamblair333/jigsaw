"""Resource reservation (spec §2): many decisions in one turn can't overspend the same gold."""

import threading

import pytest

from jigsaw.ladder import Gate, GateConfig, Ladder, Request, Verdict
from jigsaw.world import Budget


class Wants:
    def __init__(self, rung: int, choice: str, **costs: float) -> None:
        self.rung = rung
        self.choice = choice
        self.costs = costs

    def decide(self, req: Request) -> Verdict | None:
        return Verdict(choice=self.choice, rung=self.rung, reason="ok", costs=dict(self.costs))


def _req(turn: int = 3, **kw) -> Request:
    return Request(game="g", turn=turn, actor="venice", kind="recruit", situation="s", **kw)


QUIET = Gate(GateConfig(cadence=0))


# ---------------------------------------------------------------------------
# the budget itself
# ---------------------------------------------------------------------------


def test_reserve_is_all_or_nothing() -> None:
    b = Budget({"gold": 1000, "slots": 1})
    assert b.reserve({"gold": 400, "slots": 1}) is None
    assert b.remaining() == {"gold": 600, "slots": 0}
    assert b.reserve({"gold": 100, "slots": 1}) == "over budget: slots needs 1, 0 left"
    assert b.remaining() == {"gold": 600, "slots": 0}   # the gold wasn't taken either


def test_release_and_reset() -> None:
    b = Budget({"gold": 1000})
    b.reserve({"gold": 700})
    b.release({"gold": 200})
    assert b.remaining() == {"gold": 500}
    b.reset({"gold": 2000})
    assert b.remaining() == {"gold": 2000}


def test_unknown_resource_and_negative_cost_are_refused() -> None:
    b = Budget({"gold": 1000})
    assert b.reserve({"mana": 1}) == "no such resource: mana"
    assert b.reserve({"gold": -50}) == "cost of gold can't be negative (-50)"


def test_release_never_goes_above_the_total() -> None:
    b = Budget({"gold": 1000})
    b.release({"gold": 500})
    assert b.remaining() == {"gold": 1000}


# ---------------------------------------------------------------------------
# with the ladder
# ---------------------------------------------------------------------------


def test_affordable_answer_is_charged() -> None:
    b = Budget({"gold": 1000})
    v = Ladder([Wants(2, "spears", gold=300)], QUIET, budget=b).decide(_req())
    assert v.choice == "spears" and b.remaining() == {"gold": 700}
    assert v.legality[-1] == {"rung": 2, "choice": "spears", "budget": "reserved", "costs": {"gold": 300}}


def test_unaffordable_cheap_answer_passes_up() -> None:
    b = Budget({"gold": 1000})
    ladder = Ladder([Wants(2, "knights", gold=2000), Wants(7, "spears", gold=300)], QUIET, budget=b)

    v = ladder.decide(_req())

    assert (v.choice, v.rung) == ("spears", 7)
    assert "rung 2 illegal (over budget: gold needs 2000, 1000 left)" in v.reason
    assert b.remaining() == {"gold": 700}


def test_overruled_cheap_answer_costs_nothing() -> None:
    b = Budget({"gold": 1000})
    ladder = Ladder([Wants(2, "knights", gold=600), Wants(7, "spears", gold=300)], Gate(), budget=b)

    v = ladder.decide(_req(stakes=0.9))

    assert v.choice == "spears" and b.remaining() == {"gold": 700}


def test_turn_of_decisions_stops_at_the_budget() -> None:
    b = Budget({"gold": 1000})
    ladder = Ladder([Wants(2, "spears", gold=300)], QUIET, budget=b)
    choices = [ladder.decide(_req(turn=3)).choice for _ in range(4)]
    assert choices == ["spears", "spears", "spears", ""]
    assert b.remaining() == {"gold": 100}


def test_answers_without_costs_are_not_charged() -> None:
    b = Budget({"gold": 1000})
    v = Ladder([Wants(2, "hold")], QUIET, budget=b).decide(_req())
    assert v.choice == "hold" and b.remaining() == {"gold": 1000}


def test_threads_sharing_a_budget_never_overspend() -> None:
    b = Budget({"gold": 1000})
    ladder = Ladder([Wants(2, "spears", gold=100)], QUIET, budget=b)
    results: list[str] = []
    lock = threading.Lock()

    def run() -> None:
        v = ladder.decide(_req())
        with lock:
            results.append(v.choice)

    threads = [threading.Thread(target=run) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("spears") == 10
    assert b.remaining() == {"gold": 0}


def test_without_a_budget_costs_are_ignored() -> None:
    v = Ladder([Wants(2, "knights", gold=10**9)], QUIET).decide(_req())
    assert v.choice == "knights"


def test_budget_rejects_negative_totals() -> None:
    with pytest.raises(ValueError):
        Budget({"gold": -1})


def test_nan_cost_and_total_are_refused() -> None:
    b = Budget({"gold": 1000})
    assert b.reserve({"gold": float("nan")}) == "cost of gold must be a finite number (nan)"
    assert b.remaining() == {"gold": 1000}
    with pytest.raises(ValueError):
        Budget({"gold": float("nan")})


def test_float_costs_that_add_up_to_the_total_fit() -> None:
    b = Budget({"gold": 0.3})
    assert b.reserve({"gold": 0.1}) is None
    assert b.reserve({"gold": 0.2}) is None
    assert b.remaining() == {"gold": 0.0}


def test_unaffordable_intent_is_refused_before_planning() -> None:
    from typing import Any

    from jigsaw.intent import Intent

    class CountingExpander:
        calls = 0

        def expand(self, req: Request, intent: Intent, failure: str | None) -> list[dict[str, Any]] | None:
            CountingExpander.calls += 1
            return [{"op": "march"}]

    class Model:
        rung = 7

        def decide(self, req: Request) -> Verdict | None:
            return Verdict(choice="take Milan", rung=7, reason="model",
                           intent=Intent(verb="take"), costs={"gold": 2000})

    b = Budget({"gold": 1000})
    v = Ladder([Model()], Gate(), expanders={"take": CountingExpander()}, budget=b).decide(_req(stakes=0.9))

    assert CountingExpander.calls == 0
    assert "over budget: gold needs 2000, 1000 left" in v.reason
    assert "replanning" not in v.reason


def test_failed_final_charge_keeps_the_cheap_answer_in_the_log(tmp_path) -> None:
    from jigsaw.decision_log import DecisionLog

    class RacedBudget(Budget):
        """Says yes when asked, then loses the race when charged."""

        def reserve(self, costs):  # type: ignore[override]
            return "over budget: gold needs 300, 0 left"

    log = DecisionLog(tmp_path / "d.db")
    v = Ladder([Wants(2, "spears", gold=300)], QUIET, log, budget=RacedBudget({"gold": 1000})).decide(_req())

    assert (v.choice, v.rung) == ("", 0)
    row = log.get(v.decision_id)
    assert (row.cheap_choice, row.cheap_rung) == ("spears", 2)
