"""World-model pieces shared by every rung (spec section 2).

Budget is resource reservation. A turn's deciders often draw on the same gold, recruitment
slots or movement. Each answer declares what it costs (Verdict.costs). The ladder charges the
final answer to the budget, and refuses an answer the budget can't cover, so it passes up.
Later decisions in the turn see only what remains.
"""

from collections.abc import Collection, Mapping
import math
import threading
from typing import Any, cast

# Costs that add up to the total in floating point (0.1 + 0.2 vs 0.3) still fit.
_EPS = 1e-9


class Budget:
    """Totals per resource and what's left of them, safe to share between threads.

    Call reset() at the start of each turn with the new totals. Call release() when the game
    rejects an order that was charged, so its resources go back. Release before the next
    reset(): a release after it credits the new turn.
    """

    def __init__(self, totals: Mapping[str, float]) -> None:
        self._lock = threading.Lock()
        self._totals: dict[str, float] = {}
        self._left: dict[str, float] = {}
        self.reset(totals)

    def reset(self, totals: Mapping[str, float]) -> None:
        bad = {k: v for k, v in totals.items() if not (math.isfinite(v) and v >= 0)}
        if bad:
            raise ValueError(f"budget totals must be finite and not negative: {bad}")
        with self._lock:
            self._totals = dict(totals)
            self._left = dict(totals)

    def remaining(self) -> dict[str, float]:
        with self._lock:
            return dict(self._left)

    def _refusal(self, costs: Mapping[str, float]) -> str | None:
        for name, cost in costs.items():
            if name not in self._left:
                return f"no such resource: {name}"
            if not math.isfinite(cost):
                return f"cost of {name} must be a finite number ({cost})"
            if cost < 0:
                return f"cost of {name} can't be negative ({cost:g})"
            if cost > self._left[name] + _EPS:
                return f"over budget: {name} needs {cost:g}, {self._left[name]:g} left"
        return None

    def affordable(self, costs: Mapping[str, float]) -> str | None:
        """None when the costs fit what's left now, else why not. Reserves nothing."""
        with self._lock:
            return self._refusal(costs)

    def reserve(self, costs: Mapping[str, float]) -> str | None:
        """Take all of the costs, or none of them. None on success, else why not."""
        with self._lock:
            refusal = self._refusal(costs)
            if refusal is None:
                for name, cost in costs.items():
                    left = self._left[name] - cost
                    self._left[name] = 0.0 if left < _EPS else left
            return refusal

    def release(self, costs: Mapping[str, float]) -> None:
        """Give resources back, never above the turn's total."""
        with self._lock:
            for name, cost in costs.items():
                if name in self._left and cost > 0:
                    self._left[name] = min(self._totals[name], self._left[name] + cost)


class Blackboard:
    """What every rung can read about each actor. For now, persona weights (spec section 5).

    A persona weight is a number in 0..1 for a flavor such as "aggression" or "piety". A model
    sets them with a `persona` intent (see PersonaExpander), and rung-2 utility scoring reads
    them (Consideration.persona). A missing weight counts as 0.5, which changes nothing.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._persona: dict[str, dict[str, float]] = {}
        self._persona_turn: dict[str, int] = {}

    def set_persona(self, actor: str, weights: Mapping[str, object], turn: int) -> None:
        """Merge weights into the actor's persona. Raises ValueError, writing nothing, if any
        weight isn't a number in 0..1."""
        bad = {k: v for k, v in weights.items() if not _is_weight(v)}
        if bad:
            raise ValueError(f"persona weights must be numbers in 0..1: {bad}")
        clean = {k: float(v) for k, v in weights.items() if isinstance(v, (int, float))}
        with self._lock:
            self._persona.setdefault(actor, {}).update(clean)
            self._persona_turn[actor] = turn

    def persona(self, actor: str) -> dict[str, float]:
        with self._lock:
            return dict(self._persona.get(actor, {}))

    def persona_turn(self, actor: str) -> int | None:
        """The turn the actor's persona was last set, or None."""
        with self._lock:
            return self._persona_turn.get(actor)


def _is_weight(v: object) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v) and 0.0 <= v <= 1.0
    except OverflowError:   # an int too large for a float
        return False


class PersonaExpander:
    """The expander for the `persona` intent verb: args {"weights": {"aggression": 0.8}}.

    expand() only checks the weights and returns one primitive, {"op": "persona", ...}, which a
    pack can ignore or show. Invalid weights, or names outside `allowed` when it's given,
    raise, so the intent fails. The ladder calls commit() only for the answer that stands,
    after the legality and budget checks, and that is when the weights reach the blackboard.
    """

    def __init__(self, blackboard: Blackboard, allowed: Collection[str] | None = None) -> None:
        self.blackboard = blackboard
        self.allowed = set(allowed) if allowed is not None else None

    def _weights(self, intent: Any) -> dict[str, object]:
        weights = intent.args.get("weights")
        if not isinstance(weights, dict) or not weights:
            raise ValueError("a persona intent needs args {'weights': {name: number in 0..1}}")
        raw = cast(dict[object, object], weights)   # model output: checked here, not trusted
        typed: dict[str, object] = {str(k): v for k, v in raw.items()}
        if self.allowed is not None:
            unknown = sorted(set(typed) - self.allowed)
            if unknown:
                raise ValueError(f"unknown persona weight {unknown[0]!r}")
        bad = {k: v for k, v in typed.items() if not _is_weight(v)}
        if bad:
            raise ValueError(f"persona weights must be numbers in 0..1: {bad}")
        return typed

    def expand(self, req: Any, intent: Any, failure: str | None) -> list[dict[str, Any]] | None:
        return [{"op": "persona", "actor": req.actor, "weights": self._weights(intent)}]

    def commit(self, req: Any, intent: Any) -> None:
        """Write the weights; the ladder calls this once, for the answer that stands."""
        self.blackboard.set_persona(req.actor, self._weights(intent), turn=req.turn)
