"""Persona-weight intents (spec §5): a model sets flavor weights that steer rung-2 scoring."""

from typing import Any

import pytest

from jigsaw.decision_log import Option
from jigsaw.intent import Intent
from jigsaw.ladder import Gate, GateConfig, Ladder, Request, Verdict
from jigsaw.utility import Consideration, UtilityDecider, linear
from jigsaw.world import Blackboard, PersonaExpander


def _war_req(actor: str = "venice") -> Request:
    return Request(game="g", turn=4, actor=actor, kind="stance", situation="s",
                   options=[Option(name="attack"), Option(name="hold")])


AGGRO = {"attack": 1.0, "hold": 0.0}

# "attack" wins on aggression, "hold" wins on caution
CONSIDERATIONS = [
    Consideration("aggression", lambda r, o: 0.2 + 0.8 * AGGRO[o.name], linear(), persona="aggression"),
    Consideration("caution", lambda r, o: 0.2 + 0.8 * (1 - AGGRO[o.name]), linear(), persona="caution"),
]


def test_blackboard_keeps_weights_per_actor() -> None:
    bb = Blackboard()
    bb.set_persona("venice", {"aggression": 0.9}, turn=3)
    assert bb.persona("venice") == {"aggression": 0.9}
    assert bb.persona("milan") == {}
    assert bb.persona_turn("venice") == 3


def test_blackboard_refuses_weights_outside_0_1() -> None:
    bb = Blackboard()
    with pytest.raises(ValueError, match="aggression"):
        bb.set_persona("venice", {"aggression": 1.5}, turn=1)
    with pytest.raises(ValueError):
        bb.set_persona("venice", {"aggression": float("nan")}, turn=1)


def test_neutral_weights_change_nothing() -> None:
    bb = Blackboard()
    plain = UtilityDecider(considerations=CONSIDERATIONS, kinds={"stance"})
    steered = UtilityDecider(considerations=CONSIDERATIONS, kinds={"stance"}, blackboard=bb)
    bb.set_persona("venice", {"aggression": 0.5, "caution": 0.5}, turn=4)
    a, b = plain.decide(_war_req()), steered.decide(_war_req())
    assert a is not None and b is not None
    assert [o.score for o in a.options] == pytest.approx([o.score for o in b.options])


def test_weight_zero_switches_a_consideration_off() -> None:
    bb = Blackboard()
    bb.set_persona("venice", {"aggression": 1.0, "caution": 0.0}, turn=4)
    v = UtilityDecider(considerations=CONSIDERATIONS, kinds={"stance"}, blackboard=bb).decide(_war_req())
    assert v is not None and v.choice == "attack"
    bb.set_persona("venice", {"aggression": 0.0, "caution": 1.0}, turn=5)
    v = UtilityDecider(considerations=CONSIDERATIONS, kinds={"stance"}, blackboard=bb).decide(_war_req())
    assert v is not None and v.choice == "hold"


def test_weights_belong_to_one_actor() -> None:
    bb = Blackboard()
    bb.set_persona("venice", {"aggression": 1.0, "caution": 0.0}, turn=4)
    d = UtilityDecider(considerations=CONSIDERATIONS, kinds={"stance"}, blackboard=bb)
    milan = d.decide(_war_req("milan"))
    venice = d.decide(_war_req("venice"))
    assert milan is not None and venice is not None
    assert [o.score for o in milan.options] != [o.score for o in venice.options]


class PersonaModel:
    rung = 7

    def __init__(self, weights: dict[str, Any]) -> None:
        self.weights = weights

    def decide(self, req: Request) -> Verdict | None:
        return Verdict(choice="persona", rung=7, reason="model",
                       intent=Intent(verb="persona", args={"weights": self.weights}))


def _persona_req() -> Request:
    return Request(game="g", turn=4, actor="venice", kind="persona", situation="s", stakes=0.9)


def test_model_sets_the_persona_through_an_intent() -> None:
    bb = Blackboard()
    ladder = Ladder([PersonaModel({"aggression": 0.8})], Gate(),
                    expanders={"persona": PersonaExpander(bb)})

    v = ladder.decide(_persona_req())

    assert v.rung == 7
    assert bb.persona("venice") == {"aggression": 0.8}
    assert v.primitives == [{"op": "persona", "actor": "venice", "weights": {"aggression": 0.8}}]


def test_bad_persona_weights_are_refused_and_nothing_is_written() -> None:
    bb = Blackboard()
    ladder = Ladder([PersonaModel({"aggression": 7})], Gate(GateConfig(cadence=0)),
                    expanders={"persona": PersonaExpander(bb)})

    v = ladder.decide(_persona_req())

    assert v.rung == 0 and bb.persona("venice") == {}
    assert "weights must be numbers in 0..1" in v.reason


def test_persona_merges_with_earlier_weights() -> None:
    bb = Blackboard()
    bb.set_persona("venice", {"caution": 0.3}, turn=2)
    Ladder([PersonaModel({"aggression": 0.8})], Gate(),
           expanders={"persona": PersonaExpander(bb)}).decide(_persona_req())
    assert bb.persona("venice") == {"caution": 0.3, "aggression": 0.8}
