"""Decision ladder and gate for Jigsaw game AI."""

from collections.abc import Sequence
import logging
import threading
from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel, Field

from jigsaw.decision_log import Decision, DecisionLog, Option

_log = logging.getLogger("jigsaw")


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
    # the decision log's row id, set by Ladder.decide when it logs; the caller records the outcome
    # against it (DecisionLog.set_outcome) once the decision has been carried out
    decision_id: int | None = None
    # deciders that raised or timed out on the way, treated as passing up; set by Ladder.decide
    decider_errors: list[dict[str, Any]] = Field(default_factory=list)
    # the gate's reason for escalating, or "" when it didn't; set by Ladder.decide
    escalated_because: str = ""


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
    """Decision ladder managing escalation through cheap and high-level deciders.

    A decider that raises an Exception, or gives no answer within decider_timeout seconds,
    counts as passing up. The failure is named in the verdict's reason and decider_errors,
    written to the log row, and logged as a warning on the "jigsaw" logger.

    decider_timeout is off by default, and then every decider runs on the calling thread.
    When it is set, each decider runs on its own daemon thread. Python can't stop a thread,
    so a decider that times out keeps running in the background until it returns. Give
    network deciders their own client timeout too, and keep them safe to call from another
    thread while an earlier call is still running.
    """

    def __init__(
        self,
        deciders: Sequence[Decider] | list[Decider],
        gate: Gate,
        log: DecisionLog | None = None,
        decider_timeout: float | None = None,
    ) -> None:
        self.deciders = list(deciders)
        self.gate = gate
        self.log = log
        self.decider_timeout = decider_timeout

    def _ask(self, decider: Decider, req: Request, errors: list[dict[str, Any]]) -> Verdict | None:
        """Ask one decider. A raise or a timeout is recorded in errors and returns None."""
        try:
            if self.decider_timeout is None:
                return decider.decide(req)
            box: dict[str, Any] = {}

            def run() -> None:
                try:
                    box["verdict"] = decider.decide(req)
                except BaseException as exc:  # handed back to the calling thread below
                    box["exc"] = exc

            worker = threading.Thread(target=run, name=f"jigsaw-rung-{decider.rung}", daemon=True)
            worker.start()
            worker.join(self.decider_timeout)
            if worker.is_alive():
                raise TimeoutError(f"no answer within {self.decider_timeout}s")
            if "exc" in box:
                raise box["exc"]
            return box.get("verdict")
        except Exception as exc:
            errors.append({"rung": decider.rung, "error": f"{type(exc).__name__}: {exc}"})
            _log.warning(
                "rung %d decider failed on %s/%s turn %d; treated as passing up",
                decider.rung, req.game, req.kind, req.turn, exc_info=exc,
            )
            return None

    def decide(self, req: Request) -> Verdict:
        """Execute deciders and escalation gate to produce a final decision."""
        escalate_rung = self.gate.config.escalate_rung
        sorted_deciders = sorted(self.deciders, key=lambda d: d.rung)

        cheap_deciders = [d for d in sorted_deciders if d.rung < escalate_rung]
        higher_deciders = [d for d in sorted_deciders if d.rung >= escalate_rung]
        errors: list[dict[str, Any]] = []

        cheap_verdict: Verdict | None = None
        for decider in cheap_deciders:
            v = self._ask(decider, req, errors)
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
                v = self._ask(decider, req, errors)
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

        if errors:
            failed = "; ".join(f"rung {e['rung']} failed ({e['error']})" for e in errors)
            final_verdict = final_verdict.model_copy(
                update={"reason": f"{final_verdict.reason}; {failed}", "decider_errors": errors}
            )

        final_verdict = final_verdict.model_copy(update={"escalated_because": gate_reason})

        if self.log is not None:
            # On an escalation, keep the cheap answer too, so agreement can be measured later.
            keep_cheap = bool(gate_reason) and cheap_verdict is not None
            decision = Decision(
                cheap_choice=cheap_verdict.choice if keep_cheap else None,
                cheap_rung=cheap_verdict.rung if keep_cheap else None,
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
                decider_errors=errors,
                request=req.model_dump(),
            )
            final_verdict = final_verdict.model_copy(update={"decision_id": self.log.record(decision)})

        return final_verdict
