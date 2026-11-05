"""Rung-2 utility scoring (Mark, *Behavioral Mathematics for Game AI*).

A Consideration measures one thing about an option as an input in 0..1, such as "how much the
treasury needs this tax level", and passes it through a response curve. An option's score is the
product of its considerations, with Mark's compensation factor so that adding considerations
doesn't by itself drag every score toward zero. The best option wins.

The verdict carries every option with its score, and the gate's close-call check uses those
scores. So when two options score close together, the gate asks a stronger rung.
"""

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
import math

from jigsaw.decision_log import Option
from jigsaw.ladder import Request, Verdict
from jigsaw.world import Blackboard

Curve = Callable[[float], float]


def _clamp(x: float) -> float:
    """Into 0..1. NaN, which compares false with everything, becomes 0."""
    if math.isnan(x):
        return 0.0
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def linear(slope: float = 1.0, intercept: float = 0.0) -> Curve:
    """y = slope * x + intercept. linear(-1, 1) falls as the input rises."""
    return lambda x: _clamp(slope * _clamp(x) + intercept)


def power(exponent: float) -> Curve:
    """y = x ** exponent. Above 1 it rewards only high inputs; below 1 it rewards any input.

    A negative exponent is refused: it jumps from 1 to infinity at 0. Use linear(-1, 1) for a
    falling curve.
    """
    if exponent < 0:
        raise ValueError(f"power exponent must be >= 0, got {exponent}")
    return lambda x: _clamp(_clamp(x) ** exponent)


def logistic(k: float = 10.0, mid: float = 0.5) -> Curve:
    """An S-curve centred on mid; k sets how sharp the switch is."""

    def curve(x: float) -> float:
        # exp() overflows past about 709; by then the curve is 0 or 1 to machine precision
        exponent = max(-700.0, min(700.0, -k * (_clamp(x) - mid)))
        return _clamp(1.0 / (1.0 + math.exp(exponent)))

    return curve


def step(threshold: float) -> Curve:
    """0 below the threshold, 1 at or above it."""
    return lambda x: 1.0 if _clamp(x) >= threshold else 0.0


def compensate(score: float, n: int) -> float:
    """Mark's compensation factor for a product of n considerations."""
    if n <= 1:
        return score
    makeup = (1.0 - score) * (1.0 - 1.0 / n)
    return _clamp(score + makeup * score)


@dataclass(frozen=True)
class Consideration:
    """One measured input (0..1) for an option, shaped by a response curve."""

    name: str
    input: Callable[[Request, Option], float]
    curve: Curve
    # A persona weight that steers this consideration (spec §5). With a blackboard, weight w
    # raises the curve's value to the power 2w: 0.5 changes nothing, 0 switches it off, and 1
    # makes it count more sharply.
    persona: str | None = None


class UtilityDecider:
    """Scores each option on its considerations and answers with the best one.

    Passes (returns None) when the request's kind isn't in kinds, when there are no options, or
    when the best score is below min_score. A consideration that raises scores that option 0,
    and the option's note says why.
    """

    def __init__(
        self,
        considerations: Sequence[Consideration],
        rung: int = 2,
        kinds: Collection[str] | None = None,
        min_score: float = 0.0,
        blackboard: Blackboard | None = None,
    ) -> None:
        self.considerations = list(considerations)
        self.rung = rung
        self.kinds = set(kinds) if kinds is not None else None
        self.min_score = min_score
        self.blackboard = blackboard

    def score(self, req: Request, option: Option) -> Option:
        """The option with its utility score, and each consideration's value in its note."""
        product = 1.0
        parts: list[str] = []
        persona = self.blackboard.persona(req.actor) if self.blackboard is not None else {}
        for c in self.considerations:
            try:
                raw = c.input(req, option)
                value = c.curve(raw)
            except Exception as exc:
                return option.model_copy(
                    update={"score": 0.0, "note": f"{c.name} raised {type(exc).__name__}: {exc}"}
                )
            if not math.isfinite(raw):
                return option.model_copy(
                    update={"score": 0.0, "note": f"{c.name} input is not a number ({raw})"}
                )
            if c.persona is not None and c.persona in persona:
                value = value ** (2.0 * persona[c.persona])
            product *= value
            parts.append(f"{c.name}={value:.2f}")
        total = compensate(product, len(self.considerations))
        return option.model_copy(update={"score": total, "note": " ".join(parts)})

    def decide(self, req: Request) -> Verdict | None:
        if self.kinds is not None and req.kind not in self.kinds:
            return None
        if not req.options or not self.considerations:
            return None
        scored = [self.score(req, o) for o in req.options]
        if all(" raised " in o.note for o in scored):
            # a systematic bug, not a decision: raise so the ladder records it as a decider error
            raise RuntimeError(f"every option failed its considerations: {scored[0].note}")
        ranked = sorted(scored, key=lambda o: o.score or 0.0, reverse=True)
        best = ranked[0]
        if (best.score or 0.0) <= 0.0 or (best.score or 0.0) < self.min_score:
            return None
        reason = f"utility: {best.name} {best.score:.2f}"
        if len(ranked) > 1:
            reason += f" over {ranked[1].name} {ranked[1].score:.2f}"
        return Verdict(choice=best.name, rung=self.rung, reason=reason, options=scored)
