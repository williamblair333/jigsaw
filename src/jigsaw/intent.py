"""The intent contract (spec section 5).

A model rung answers with an Intent: a goal such as `take` with names as arguments
({"target": "Milan"}), never coordinates or unit ids. The pack's Expander for that verb turns
the intent into primitives. The legality check then runs on the expanded plan. If the plan
fails, the expander gets one more try with the failure reason.
"""

from typing import Any, Protocol, runtime_checkable
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


@runtime_checkable
class Expander(Protocol):
    """Turns an intent into primitives, or returns None when it finds no plan.

    failure is None on the first try. On the replan it holds why the first plan failed
    (the legality check's reason, or what went wrong in the expander).
    """

    def expand(self, req: Any, intent: Intent, failure: str | None) -> list[dict[str, Any]] | None:
        ...
