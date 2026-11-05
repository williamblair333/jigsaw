"""The intent contract (spec section 5).

A model rung answers with an Intent: a goal such as `take` with names as arguments
({"target": "Milan"}), never coordinates or unit ids. The pack's Expander for that verb turns
the intent into primitives. The legality check then runs on the expanded plan. If the plan
fails, the expander gets one more try with the failure reason.
"""

from typing import Any, Protocol, cast, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid4().hex


class Intent(BaseModel):
    """A goal a model chose, for a pack's expander to plan."""

    id: str = Field(default_factory=_new_id)
    verb: str
    args: dict[str, Any] = Field(default_factory=dict[str, Any])
    note: str = ""


class Holding(BaseModel):
    """A model rung's holding (STANDARDS idea holdings-for-distillation): "when these hold,
    choose this". Distillation turns logged holdings into rung-1 rules (jigsaw.distill).

    `when` maps a request.context key to a condition: a plain value must be equal, a list
    means one of, and {"min": a, "max": b} is a numeric range (either end may be left out).
    """

    when: dict[str, Any] = Field(default_factory=dict[str, Any])
    choose: str
    kind: str = ""
    # the decision log row the holding came from, when read back from a log
    source_id: int | None = None

    def matches(self, context: dict[str, Any]) -> bool:
        for key, cond in self.when.items():
            if key not in context:
                return False
            value = context[key]
            if isinstance(cond, dict):
                bounds = cast(dict[str, Any], cond)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return False
                if "min" in bounds and value < bounds["min"]:
                    return False
                if "max" in bounds and value > bounds["max"]:
                    return False
            elif isinstance(cond, list):
                if value not in cast(list[Any], cond):
                    return False
            elif value != cond:
                return False
        return True


@runtime_checkable
class Expander(Protocol):
    """Turns an intent into primitives, or returns None when it finds no plan.

    failure is None on the first try. On the replan it holds why the first plan failed
    (the legality check's reason, or what went wrong in the expander).

    An expander may also define commit(req, intent). The ladder calls it once, only for the
    answer that stands, after the legality and budget checks. Put side effects there, not in
    expand(), which may run twice and may be refused.
    """

    def expand(self, req: Any, intent: Intent, failure: str | None) -> list[dict[str, Any]] | None:
        ...
