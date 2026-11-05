"""The intent contract (spec section 5).

A model rung answers with an Intent: a goal such as `take` with names as arguments
({"target": "Milan"}), never coordinates or unit ids. The pack's Expander for that verb turns
the intent into primitives. The legality check then runs on the expanded plan. If the plan
fails, the expander gets one more try with the failure reason.
"""

import math
from typing import Any, Protocol, cast, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


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

    when: dict[str, Any]
    choose: str
    kind: str = ""
    game: str = ""
    # the decision log row the holding came from, when read back from a log
    source_id: int | None = None

    @field_validator("when")
    @classmethod
    def _check_when(cls, when: dict[str, Any]) -> dict[str, Any]:
        # A holding comes from model output, so a malformed one must fail here, not later in
        # every reader: an empty `when` would match everything, and {"mn": 5} would too.
        if not when:
            raise ValueError("a holding needs at least one condition in `when`")
        for key, cond in when.items():
            if isinstance(cond, dict):
                bounds = cast(dict[str, Any], cond)
                if not bounds or set(bounds) - {"min", "max"}:
                    raise ValueError(f"{key}: a range is {{'min': a, 'max': b}}, got {bounds}")
                for b in bounds.values():
                    if not _is_number(b):
                        raise ValueError(f"{key}: range bounds must be numbers, got {b!r}")
            elif isinstance(cond, list):
                for item in cast(list[Any], cond):
                    if not _is_scalar(item):
                        raise ValueError(f"{key}: list items must be plain values, got {item!r}")
            elif not _is_scalar(cond):
                raise ValueError(f"{key}: a condition is a value, a list or a range, got {cond!r}")
        return when

    def matches(self, context: dict[str, Any]) -> bool:
        for key, cond in self.when.items():
            if key not in context:
                return False
            value = context[key]
            if isinstance(cond, dict):
                bounds = cast(dict[str, Any], cond)
                if not _is_number(value):
                    return False
                if "min" in bounds and value < bounds["min"]:
                    return False
                if "max" in bounds and value > bounds["max"]:
                    return False
            elif isinstance(cond, list):
                if not any(_same(value, c) for c in cast(list[Any], cond)):
                    return False
            elif not _same(value, cond):
                return False
        return True


def _is_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _is_scalar(v: object) -> bool:
    if isinstance(v, float):
        return math.isfinite(v)
    return v is None or isinstance(v, (str, int, bool))


def _same(a: object, b: object) -> bool:
    """Equal, and a bool only equals a bool (in Python, True == 1)."""
    return isinstance(a, bool) == isinstance(b, bool) and a == b


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
