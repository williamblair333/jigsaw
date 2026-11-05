"""World-model pieces shared by every rung (spec section 2).

Budget is resource reservation. A turn's deciders often draw on the same gold, recruitment
slots or movement. Each answer declares what it costs (Verdict.costs). The ladder charges the
final answer to the budget, and refuses an answer the budget can't cover, so it passes up.
Later decisions in the turn see only what remains.
"""

from collections.abc import Mapping
import threading


class Budget:
    """Totals per resource and what's left of them, safe to share between threads.

    Call reset() at the start of each turn with the new totals. Call release() when the game
    rejects an order that was charged, so its resources go back.
    """

    def __init__(self, totals: Mapping[str, float]) -> None:
        self._lock = threading.Lock()
        self._totals: dict[str, float] = {}
        self._left: dict[str, float] = {}
        self.reset(totals)

    def reset(self, totals: Mapping[str, float]) -> None:
        bad = {k: v for k, v in totals.items() if v < 0}
        if bad:
            raise ValueError(f"budget totals can't be negative: {bad}")
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
            if cost < 0:
                return f"cost of {name} can't be negative ({cost:g})"
            if cost > self._left[name]:
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
                    self._left[name] -= cost
            return refusal

    def release(self, costs: Mapping[str, float]) -> None:
        """Give resources back, never above the turn's total."""
        with self._lock:
            for name, cost in costs.items():
                if name in self._left and cost > 0:
                    self._left[name] = min(self._totals[name], self._left[name] + cost)
