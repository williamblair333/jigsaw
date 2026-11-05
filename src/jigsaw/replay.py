"""Rerun logged decisions through a candidate gate or ladder, offline.

replay_gate asks only "would this gate have escalated?". It runs no deciders: the cheap
rung's answer is already in the log (cheap_choice, or the choice of a row that didn't
escalate). So you can try new thresholds on a whole campaign for free.

replay_ladder runs the candidate ladder's deciders for real. A model rung makes real calls,
which may cost money. Neither function writes to any log.
"""

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, Field

from jigsaw.decision_log import Decision, DecisionLog
from jigsaw.ladder import Gate, Ladder, Request, Verdict


class ReplayRow(BaseModel):
    """One logged decision next to what the candidate does with it."""

    decision_id: int
    game: str
    actor: str
    kind: str
    turn: int
    logged_choice: str
    logged_rung: int
    logged_escalated: str
    # None when the candidate gate escalates a row the log didn't: only a model could say.
    new_choice: str | None
    new_rung: int | None
    new_escalated: str

    @property
    def changed_choice(self) -> bool:
        return self.new_choice is not None and self.new_choice != self.logged_choice


class ReplayReport(BaseModel):
    rows: list[ReplayRow] = Field(default_factory=list)
    # ids of rows logged before the request was stored (schema 3), so they can't be replayed
    skipped: list[int] = Field(default_factory=list)

    @property
    def escalated_before(self) -> int:
        return sum(1 for r in self.rows if r.logged_escalated)

    @property
    def escalated_now(self) -> int:
        return sum(1 for r in self.rows if r.new_escalated)

    @property
    def changed_choices(self) -> int:
        return sum(1 for r in self.rows if r.changed_choice)

    @property
    def needs_model(self) -> int:
        return sum(1 for r in self.rows if r.new_choice is None)

    def summary(self) -> str:
        lines = [
            f"{len(self.rows)} rows replayed, {len(self.skipped)} skipped (logged before the "
            "request was stored)",
            f"escalated: {self.escalated_before} logged, {self.escalated_now} now",
            f"choice would change: {self.changed_choices}",
        ]
        if self.needs_model:
            lines.append(f"newly escalated, answer unknown without a model: {self.needs_model}")
        return "\n".join(lines)


def _logged(log: DecisionLog, filters: dict[str, Any], report: ReplayReport) -> Iterator[tuple[Decision, Request]]:
    for d in log.query(**filters):
        if d.request is None:
            assert d.id is not None
            report.skipped.append(d.id)
            continue
        yield d, Request.model_validate(d.request)


def _row(d: Decision, choice: str | None, rung: int | None, escalated: str) -> ReplayRow:
    assert d.id is not None
    return ReplayRow(
        decision_id=d.id, game=d.game, actor=d.actor, kind=d.kind, turn=d.turn,
        logged_choice=d.choice, logged_rung=d.rung, logged_escalated=d.escalated_because,
        new_choice=choice, new_rung=rung, new_escalated=escalated,
    )


def _cheap_verdict(d: Decision) -> Verdict | None:
    """What the cheap rungs answered when this row was logged, or None if none did."""
    if d.cheap_choice is not None and d.cheap_rung is not None:
        return Verdict(choice=d.cheap_choice, rung=d.cheap_rung, reason="logged cheap answer")
    if not d.escalated_because and d.choice:
        return Verdict(choice=d.choice, rung=d.rung, reason="logged answer")
    return None


def replay_gate(log: DecisionLog, gate: Gate, **filters: Any) -> ReplayReport:
    """Ask a candidate gate about each logged row. Filters are those of DecisionLog.query.

    When the candidate stays quiet, the new choice is the logged cheap answer. When both
    escalate, the logged model answer is assumed to stand. When only the candidate escalates,
    the new choice is unknown (None).
    """
    report = ReplayReport()
    for d, req in _logged(log, filters, report):
        cheap = _cheap_verdict(d)
        reason = gate.check(req, cheap)
        if not reason:
            choice, rung = (cheap.choice, cheap.rung) if cheap else ("", 0)
        elif d.escalated_because:
            choice, rung = d.choice, d.rung
        else:
            choice, rung = None, None
        report.rows.append(_row(d, choice, rung, reason))
    return report


def replay_ladder(log: DecisionLog, ladder: Ladder, **filters: Any) -> ReplayReport:
    """Run each logged request through a candidate ladder. Its deciders run for real; its log
    is not written to."""
    offline = Ladder(ladder.deciders, ladder.gate, log=None, decider_timeout=ladder.decider_timeout)
    report = ReplayReport()
    for d, req in _logged(log, filters, report):
        v = offline.decide(req)
        report.rows.append(_row(d, v.choice, v.rung, v.escalated_because))
    return report
