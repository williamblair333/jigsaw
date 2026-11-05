"""Rung-2 utility scoring: considerations through response curves (Mark, Behavioral Mathematics)."""

import math

import pytest

from jigsaw.decision_log import Option
from jigsaw.ladder import Gate, GateConfig, Ladder, Request, Verdict
from jigsaw.utility import Consideration, UtilityDecider, compensate, linear, logistic, power, step


# ---------------------------------------------------------------------------
# response curves: every curve maps 0..1 into 0..1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("curve", [linear(), linear(-1, 1), power(2), power(0.5), logistic(), step(0.5)])
def test_curves_stay_in_0_1_even_for_inputs_outside_it(curve) -> None:
    for x in (-1.0, 0.0, 0.25, 0.5, 0.75, 1.0, 2.0, float("nan"), float("inf")):
        assert 0.0 <= curve(x) <= 1.0


def test_curve_shapes() -> None:
    assert linear()(0.3) == pytest.approx(0.3)
    assert linear(-1, 1)(0.3) == pytest.approx(0.7)        # falls as the input rises
    assert power(2)(0.5) == pytest.approx(0.25)
    assert logistic(k=10, mid=0.5)(0.5) == pytest.approx(0.5)
    assert logistic(k=10, mid=0.5)(0.9) > 0.95
    assert (step(0.5)(0.49), step(0.5)(0.5)) == (0.0, 1.0)


def test_compensation_lifts_products_of_many_considerations() -> None:
    assert compensate(0.5, 1) == pytest.approx(0.5)        # one consideration: unchanged
    raw = 0.9 ** 4
    assert compensate(raw, 4) > raw                        # four 0.9s shouldn't sink to 0.66
    assert compensate(0.0, 4) == 0.0 and compensate(1.0, 4) == 1.0


# ---------------------------------------------------------------------------
# the decider
# ---------------------------------------------------------------------------


def _tax_req(treasury: float, unrest: float) -> Request:
    return Request(game="g", turn=5, actor="france", kind="set_tax", situation="s",
                   options=[Option(name="low"), Option(name="normal"), Option(name="high")],
                   context={"treasury_need": treasury, "unrest": unrest})


LEVEL = {"low": 0.0, "normal": 0.5, "high": 1.0}

TAX = UtilityDecider(
    kinds={"set_tax"},
    considerations=[
        # more tax when the treasury needs it
        Consideration("need", lambda r, o: 1 - abs(r.context["treasury_need"] - LEVEL[o.name]), linear()),
        # less tax when the town is restless
        Consideration("calm", lambda r, o: r.context["unrest"] * LEVEL[o.name], linear(-1, 1)),
    ],
)


def test_picks_the_best_option_and_explains_it() -> None:
    v = TAX.decide(_tax_req(treasury=0.9, unrest=0.1))
    assert v is not None and (v.choice, v.rung) == ("high", 2)
    assert v.reason.startswith("utility: high")


def test_restless_town_gets_lower_tax() -> None:
    v = TAX.decide(_tax_req(treasury=0.9, unrest=0.9))
    assert v is not None and v.choice in {"low", "normal"}


def test_verdict_carries_its_scored_options() -> None:
    v = TAX.decide(_tax_req(treasury=0.9, unrest=0.1))
    assert v is not None
    assert [o.name for o in v.options] == ["low", "normal", "high"]
    assert all(o.score is not None and 0 <= o.score <= 1 for o in v.options)
    assert "need=" in v.options[2].note and "calm=" in v.options[2].note


def test_other_kinds_pass() -> None:
    req = Request(game="g", turn=5, actor="a", kind="recruit", situation="s", options=[Option(name="x")])
    assert TAX.decide(req) is None


def test_no_options_passes() -> None:
    req = Request(game="g", turn=5, actor="a", kind="set_tax", situation="s")
    assert TAX.decide(req) is None


def test_below_min_score_passes() -> None:
    picky = UtilityDecider(considerations=TAX.considerations, min_score=0.99)
    assert picky.decide(_tax_req(treasury=0.5, unrest=0.5)) is None


def test_consideration_that_raises_scores_that_option_zero() -> None:
    broken = UtilityDecider(considerations=[
        Consideration("boom", lambda r, o: 1 / 0 if o.name == "high" else 0.8, linear()),
    ])
    v = broken.decide(_tax_req(0.5, 0.5))
    assert v is not None and v.choice != "high"
    high = next(o for o in v.options if o.name == "high")
    assert high.score == 0.0 and "ZeroDivisionError" in high.note


# ---------------------------------------------------------------------------
# with the gate: the decider's own scores drive the close call
# ---------------------------------------------------------------------------


class Model:
    rung = 7

    def decide(self, req: Request) -> Verdict | None:
        return Verdict(choice="normal", rung=7, reason="model")


def test_gate_escalates_on_the_deciders_close_call() -> None:
    even = UtilityDecider(considerations=[Consideration("flat", lambda r, o: 0.5, linear())])
    v = Ladder([even, Model()], Gate(GateConfig(cadence=0))).decide(_tax_req(0.5, 0.5))
    assert v.rung == 7 and v.escalated_because.startswith("close call")


def test_gate_stays_quiet_on_a_clear_winner() -> None:
    v = Ladder([TAX, Model()], Gate(GateConfig(cadence=0))).decide(_tax_req(treasury=0.95, unrest=0.0))
    assert (v.rung, v.choice) == (2, "high") and v.escalated_because == ""


def test_nan_input_scores_zero_and_cannot_win() -> None:
    vals = {"low": 0.3, "normal": float("nan"), "high": 0.9}
    d = UtilityDecider(considerations=[Consideration("v", lambda r, o: vals[o.name], linear())])
    v = d.decide(_tax_req(0.5, 0.5))
    assert v is not None and v.choice == "high"
    normal = next(o for o in v.options if o.name == "normal")
    assert normal.score == 0.0 and "not a number" in normal.note


def test_every_option_failing_raises_so_the_ladder_records_it() -> None:
    broken = UtilityDecider(considerations=[
        Consideration("missing", lambda r, o: r.context["no_such_key"], linear()),
    ])
    with pytest.raises(RuntimeError, match="every option failed"):
        broken.decide(_tax_req(0.5, 0.5))
    v = Ladder([broken], Gate(GateConfig(cadence=0))).decide(_tax_req(0.5, 0.5))
    assert v.rung == 0 and "every option failed" in v.decider_errors[0]["error"]


def test_all_zero_scores_pass() -> None:
    zero = UtilityDecider(considerations=[Consideration("z", lambda r, o: 0.0, linear())])
    assert zero.decide(_tax_req(0.5, 0.5)) is None


def test_power_rejects_negative_exponents() -> None:
    with pytest.raises(ValueError, match="exponent"):
        power(-1)


def test_logistic_does_not_overflow() -> None:
    c = logistic(k=5000, mid=0.5)
    assert c(0.0) == pytest.approx(0.0) and c(1.0) == pytest.approx(1.0)


def test_log_keeps_the_final_verdicts_scores(tmp_path) -> None:
    from jigsaw.decision_log import DecisionLog

    class Scored:
        rung = 7

        def decide(self, req: Request) -> Verdict | None:
            return Verdict(choice="low", rung=7, reason="model",
                           options=[Option(name="low", score=0.9), Option(name="high", score=0.1)])

    log = DecisionLog(tmp_path / "d.db")
    v = Ladder([TAX, Scored()], Gate(), log).decide(
        _tax_req(0.9, 0.1).model_copy(update={"stakes": 0.9}))
    row = log.get(v.decision_id)
    assert (row.choice, row.cheap_choice) == ("low", "high")
    assert [(o.name, o.score) for o in row.options] == [("low", 0.9), ("high", 0.1)]


def test_logistic_midpoint_is_symmetric() -> None:
    c = logistic(k=8, mid=0.5)
    assert c(0.3) == pytest.approx(1 - c(0.7))
    assert not math.isnan(c(0.5))
