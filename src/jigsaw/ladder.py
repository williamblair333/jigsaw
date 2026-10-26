"""Decision ladder and gate for Jigsaw game AI."""

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel, Field

from jigsaw.decision_log import Decision, DecisionLog, Option


class Request(BaseModel):
    """Input request describing a game decision situation."""

    game: str
    turn: int
    actor: str
    kind: str
    situation: str
    options: list[Option] = Field(default_factory=list)
    stakes: float = 0.0
    human: bool = False
    context: dict[str, Any] = Field(default_factory=dict)


class Verdict(BaseModel):
    """The decision reached by a ladder rung."""

    choice: str
    rung: int = Field(ge=0, le=7)
    reason: str
    primitives: list[dict[str, Any]] = Field(default_factory=list)


@runtime_checkable
class Decider(Protocol):
    """Protocol for deciders operating at a specific ladder rung."""

    rung: int

    def decide(self, req: Request) -> Verdict | None:
        """Return a Verdict for the request, or None to pass up."""
        ...


def normalise(options: list[Option]) -> list[Option]:
    """Scores on a 0..1 scale for the gate.

    Scores already within 0..1 are kept: they're probabilities or utilities the game pack
    calibrated, and min-max would turn any two options into 1.0 vs 0.0 and hide a close call.
    Otherwise min-max to 0..1; if all scored options are equal, each gets 1.0.
    Options with no score remain None.
    """
    scored = [opt.score for opt in options if opt.score is not None]
    if not scored:
        return [opt.model_copy() for opt in options]
    if all(0.0 <= s <= 1.0 for s in scored):
        return [opt.model_copy() for opt in options]

    min_score = min(scored)
    max_score = max(scored)

    if max_score == min_score:
        return [
            opt.model_copy(update={"score": 1.0}) if opt.score is not None else opt.model_copy()
            for opt in options
        ]

    diff = max_score - min_score
    return [
        opt.model_copy(update={"score": (opt.score - min_score) / diff})
        if opt.score is not None
        else opt.model_copy()
        for opt in options
    ]


class GateConfig(BaseModel):
    """Configuration thresholds for the decision escalation gate."""

    margin: float = 0.1
    stakes_threshold: float = 0.7
    cadence: int = 10
    escalate_rung: int = 5


class Gate:
    """Escalation gate determining when a decision should climb the ladder."""

    def __init__(self, config: GateConfig | None = None) -> None:
        self.config = config if config is not None else GateConfig()

    def check(self, req: Request, verdict: Verdict | None) -> str:
        """Check whether the request should escalate, returning the reason or empty string."""
        if req.human:
            return "human involved"
        if req.stakes >= self.config.stakes_threshold:
            return f"high stakes ({req.stakes:.2f})"
        if verdict is None:
            return "novelty: no rule matched"
        norm_opts = normalise(req.options)
        scored = sorted(
            [opt.score for opt in norm_opts if opt.score is not None],
            reverse=True,
        )
        if len(scored) >= 2:
            a, b = scored[0], scored[1]
            if round(a - b, 9) < round(self.config.margin, 9):
                return f"close call ({a:.2f} vs {b:.2f})"
        if self.config.cadence > 0 and req.turn > 0 and req.turn % self.config.cadence == 0:
            return f"cadence review (turn {req.turn})"
        return ""


class Ladder:
    """Decision ladder managing escalation through cheap and high-level deciders."""

    def __init__(
        self,
        deciders: Sequence[Decider] | list[Decider],
        gate: Gate,
        log: DecisionLog | None = None,
    ) -> None:
        self.deciders = list(deciders)
        self.gate = gate
        self.log = log

    def decide(self, req: Request) -> Verdict:
        """Execute deciders and escalation gate to produce a final decision."""
        escalate_rung = self.gate.config.escalate_rung
        sorted_deciders = sorted(self.deciders, key=lambda d: d.rung)

        cheap_deciders = [d for d in sorted_deciders if d.rung < escalate_rung]
        higher_deciders = [d for d in sorted_deciders if d.rung >= escalate_rung]

        cheap_verdict: Verdict | None = None
        for decider in cheap_deciders:
            v = decider.decide(req)
            if v is not None:
                cheap_verdict = v
                break

        gate_reason = self.gate.check(req, cheap_verdict)

        if not gate_reason:
            if cheap_verdict is not None:
                final_verdict = cheap_verdict
            else:
                final_verdict = Verdict(
                    choice="",
                    rung=0,
                    reason="no decider answered; the game's own AI keeps it",
                )
        else:
            higher_verdict: Verdict | None = None
            for decider in higher_deciders:
                v = decider.decide(req)
                if v is not None:
                    higher_verdict = v.model_copy(
                        update={"reason": f"{gate_reason}; {v.reason}"}
                    )
                    break

            if higher_verdict is not None:
                final_verdict = higher_verdict
            elif cheap_verdict is not None:
                final_verdict = cheap_verdict.model_copy(
                    update={"reason": f"{gate_reason} (no higher rung available); {cheap_verdict.reason}"}
                )
            else:
                final_verdict = Verdict(
                    choice="",
                    rung=0,
                    reason="no decider answered; the game's own AI keeps it",
                )

        if self.log is not None:
            decision = Decision(
                game=req.game,
                turn=req.turn,
                actor=req.actor,
                kind=req.kind,
                situation=req.situation,
                options=normalise(req.options),
                rung=final_verdict.rung,
                escalated_because=gate_reason,
                choice=final_verdict.choice,
                primitives=final_verdict.primitives,
            )
            self.log.record(decision)

        return final_verdict
