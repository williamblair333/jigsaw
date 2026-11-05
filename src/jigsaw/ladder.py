"""Decision ladder and gate for Jigsaw game AI."""

from collections.abc import Callable, Mapping, Sequence
import logging
import threading
from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel, Field

from jigsaw.decision_log import Decision, DecisionLog, Option
from jigsaw.intent import Expander, Intent
from jigsaw.world import Budget

_log = logging.getLogger("jigsaw")


class Request(BaseModel):
    """Input request describing a game decision situation."""

    game: str
    turn: int
    actor: str
    kind: str
    situation: str
    options: list[Option] = Field(default_factory=list[Option])
    stakes: float = 0.0
    human: bool = False
    context: dict[str, Any] = Field(default_factory=dict[str, Any])
    # What already failed on this decision, oldest first: entries the caller passes in (say,
    # "the game rejected step 2"), then each decider error and refusal the ladder met on the way
    # up. A rung asked after a failure gets a copy of the request with the trace so far.
    trace: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])


class Verdict(BaseModel):
    """The decision reached by a ladder rung."""

    choice: str
    rung: int = Field(ge=0, le=7)
    reason: str
    primitives: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    # the decision log's row id, set by Ladder.decide when it logs; the caller records the outcome
    # against it (DecisionLog.set_outcome) once the decision has been carried out
    decision_id: int | None = None
    # deciders that raised or timed out on the way, treated as passing up; set by Ladder.decide
    decider_errors: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    # the gate's reason for escalating, or "" when it didn't; set by Ladder.decide
    escalated_because: str = ""
    # why the log write failed, when it did; the verdict stands and decision_id stays None
    log_error: str | None = None
    # the pack's legality and budget checks on each answer, in order:
    # {"rung", "choice", "legal": bool, "reason" when refused}, plus intent attempts
    # ("intent_id", "attempt") and the budget charge ({"budget": "reserved", "costs"}, no "legal")
    legality: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]])
    # a model rung's goal, expanded into primitives by the pack's expander for its verb
    intent: Intent | None = None
    # the options as this decider scored them (a utility rung sets these); when present, the
    # gate's close-call check and the log use them instead of the request's own scores
    options: list[Option] = Field(default_factory=list[Option])
    # what carrying out this answer uses up, per resource; a Ladder with a budget charges it
    costs: dict[str, float] = Field(default_factory=dict[str, float])


# A pack's legality check: return None when the verdict can be sent, or the reason it can't.
Legality = Callable[["Request", Verdict], "str | None"]


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
        # a decider that scored the options itself (a utility rung) is judged on its own scores
        norm_opts = normalise(verdict.options or req.options)
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

    legality is the pack's last gate before a move reaches the game. It runs on every answer a
    decider gives. An answer it refuses counts as passing up, and so does one it can't check
    because the check itself raised: an unverified move is never returned.
    """

    def __init__(
        self,
        deciders: Sequence[Decider] | list[Decider],
        gate: Gate,
        log: DecisionLog | None = None,
        decider_timeout: float | None = None,
        legality: Legality | None = None,
        expanders: Mapping[str, Expander] | None = None,
        budget: Budget | None = None,
    ) -> None:
        self.deciders = list(deciders)
        self.gate = gate
        self.log = log
        self.decider_timeout = decider_timeout
        self.legality = legality
        # verb -> the pack's expander. When set, model rungs must answer with an intent.
        self.expanders = dict(expanders) if expanders is not None else None
        # the turn's resources; an answer it can't cover passes up, and the final one is charged
        self.budget = budget
        # log writes that failed; each such verdict was still returned, with log_error set
        self.log_failures = 0

    def _check(self, req: Request, v: Verdict) -> str | None:
        """Why the verdict can't be sent (illegal, or more than the budget has left), or None."""
        if self.legality is not None:
            try:
                refusal = self.legality(req, v)
            except Exception as exc:
                refusal = f"legality check raised {type(exc).__name__}: {exc}"
            if refusal is not None:
                return refusal
        if self.budget is not None and v.costs:
            return self.budget.affordable(v.costs)
        return None

    def _refuse(
        self, decider: Decider, req: Request, v: Verdict, reason: str,
        checks: list[dict[str, Any]], **extra: Any,
    ) -> None:
        checks.append({"rung": decider.rung, "choice": v.choice, "legal": False,
                       "reason": reason, **extra})
        _log.warning(
            "rung %d answer %r refused on %s/%s turn %d: %s",
            decider.rung, v.choice, req.game, req.kind, req.turn, reason,
        )

    def _ask(
        self,
        decider: Decider,
        req: Request,
        errors: list[dict[str, Any]],
        checks: list[dict[str, Any]],
    ) -> Verdict | None:
        """Ask one decider, expand its intent if it has one, and run the legality check.

        Anything refused returns None, so the ladder moves on as if the decider had passed.
        """
        v = self._call(decider, req, errors)
        if v is None:
            return None
        if self.expanders is not None and decider.rung >= self.gate.config.escalate_rung:
            if v.primitives:
                self._refuse(decider, req, v, "model rungs answer with an intent, not primitives",
                             checks)
                return None
            if v.intent is None:
                self._refuse(decider, req, v,
                             "model rungs answer with an intent; this answer had none", checks)
                return None
        if v.intent is not None:
            if self.expanders is None:
                self._refuse(decider, req, v,
                             "an intent needs an expander, and none are configured", checks,
                             intent_id=v.intent.id)
                return None
            return self._expand(decider, req, v, v.intent, checks)
        if self.legality is None and self.budget is None:
            return v
        refusal = self._check(req, v)
        if refusal is not None:
            self._refuse(decider, req, v, refusal, checks)
            return None
        checks.append({"rung": decider.rung, "choice": v.choice, "legal": True})
        return v

    def _expand(
        self, decider: Decider, req: Request, v: Verdict, intent: Intent,
        checks: list[dict[str, Any]],
    ) -> Verdict | None:
        """Plan the intent, check the plan, and replan once with the failure reason."""
        assert self.expanders is not None
        expander = self.expanders.get(intent.verb)
        if expander is None:
            self._refuse(decider, req, v, f"no expander for intent verb {intent.verb!r}", checks,
                         intent_id=intent.id)
            return None
        failure: str | None = None
        # the costs are the answer's, not the plan's: if it can't be paid for, don't plan it
        if self.budget is not None and v.costs:
            over = self.budget.affordable(v.costs)
            if over is not None:
                self._refuse(decider, req, v, over, checks, intent_id=intent.id)
                return None
        for attempt in (1, 2):
            tag = {"rung": decider.rung, "choice": v.choice, "intent_id": intent.id,
                   "attempt": attempt}
            try:
                primitives = expander.expand(req, intent, failure)
            except Exception as exc:
                primitives = None
                failure = f"expander raised {type(exc).__name__}: {exc}"
            else:
                if primitives is None:
                    failure = "the expander found no plan"
                elif not primitives:
                    primitives = None
                    failure = "the expander returned an empty plan"
            if primitives is not None:
                planned = v.model_copy(update={"primitives": primitives})
                refusal = self._check(req, planned)
                if refusal is None:
                    checks.append({**tag, "legal": True})
                    return planned
                failure = refusal
            # every failed attempt is kept; only the final refusal goes into the reason text
            checks.append({**tag, "legal": False, "reason": failure})
        self._refuse(decider, req, v, f"intent {intent.verb} failed after replanning: {failure}",
                     checks, intent_id=intent.id)
        return None

    def _call(self, decider: Decider, req: Request, errors: list[dict[str, Any]]) -> Verdict | None:
        """Call one decider. A raise or a timeout is recorded in errors and returns None."""
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
        checks: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = list(req.trace)

        def ask(decider: Decider) -> Verdict | None:
            """Ask one decider with the trace so far, then add what failed to the trace."""
            seen_errors, seen_checks = len(errors), len(checks)
            asked = req if len(trace) == len(req.trace) else req.model_copy(update={"trace": list(trace)})
            v = self._ask(decider, asked, errors, checks)
            trace.extend(errors[seen_errors:])
            trace.extend(c for c in checks[seen_checks:] if not c["legal"])
            return v

        cheap_verdict: Verdict | None = None
        for decider in cheap_deciders:
            v = ask(decider)
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
                v = ask(decider)
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

        charge_failed = False
        if self.budget is not None and final_verdict.costs and final_verdict.choice:
            # Charge only the answer that stands. Atomic, so threads sharing a budget can't both
            # spend the last of it. The loser falls back to the game's own AI, deliberately:
            # its answer was judged with gold that is no longer there.
            refusal = self.budget.reserve(final_verdict.costs)
            charge_failed = refusal is not None
            if refusal is None:
                checks.append({"rung": final_verdict.rung, "choice": final_verdict.choice,
                               "budget": "reserved", "costs": dict(final_verdict.costs)})
            else:
                checks.append({"rung": final_verdict.rung, "choice": final_verdict.choice,
                               "legal": False, "reason": refusal})
                final_verdict = Verdict(
                    choice="", rung=0, reason="no affordable answer; the game's own AI keeps it"
                )

        # An expander may have a commit(req, intent) step, run once for the answer that stands,
        # after every check (PersonaExpander writes its weights here, not while planning).
        if final_verdict.intent is not None and self.expanders is not None and final_verdict.choice:
            commit = getattr(self.expanders.get(final_verdict.intent.verb), "commit", None)
            if callable(commit):
                try:
                    commit(req, final_verdict.intent)
                except Exception as exc:
                    errors.append({"rung": final_verdict.rung,
                                   "error": f"commit raised {type(exc).__name__}: {exc}"})
                    _log.warning("intent %s commit failed on %s/%s turn %d",
                                 final_verdict.intent.verb, req.game, req.kind, req.turn,
                                 exc_info=exc)

        if errors:
            failed = "; ".join(f"rung {e['rung']} failed ({e['error']})" for e in errors)
            final_verdict = final_verdict.model_copy(
                update={"reason": f"{final_verdict.reason}; {failed}", "decider_errors": errors}
            )

        # per-attempt entries of an intent stay in legality; the final refusal speaks for them
        refused = [c for c in checks if not c.get("legal", True) and "attempt" not in c]
        if refused:
            text = "; ".join(f"rung {c['rung']} illegal ({c['reason']})" for c in refused)
            final_verdict = final_verdict.model_copy(
                update={"reason": f"{final_verdict.reason}; {text}"}
            )

        final_verdict = final_verdict.model_copy(
            update={"escalated_because": gate_reason, "legality": checks}
        )

        if self.log is not None:
            try:
                final_verdict = self._record(req, final_verdict, cheap_verdict, gate_reason, errors,
                                             charge_failed)
            except Exception as exc:
                # Losing one log row is recoverable; losing the turn is not.
                self.log_failures += 1
                final_verdict = final_verdict.model_copy(
                    update={"log_error": f"{type(exc).__name__}: {exc}"}
                )
                _log.warning(
                    "decision on %s/%s turn %d not logged (%d failed writes so far)",
                    req.game, req.kind, req.turn, self.log_failures, exc_info=exc,
                )

        return final_verdict

    def _record(
        self,
        req: Request,
        final_verdict: Verdict,
        cheap_verdict: Verdict | None,
        gate_reason: str,
        errors: list[dict[str, Any]],
        charge_failed: bool = False,
    ) -> Verdict:
        """Write the decision to the log and return the verdict with its decision_id."""
        assert self.log is not None
        # On an escalation, keep the cheap answer too, so agreement can be measured later.
        # (also when the budget couldn't pay for the answer that stood: the row says choice "",
        # and replay must still know what the cheap rung said)
        keep_cheap = (bool(gate_reason) or charge_failed) and cheap_verdict is not None
        decision = Decision(
            cheap_choice=cheap_verdict.choice if keep_cheap and cheap_verdict else None,
            cheap_rung=cheap_verdict.rung if keep_cheap and cheap_verdict else None,
            game=req.game,
            turn=req.turn,
            actor=req.actor,
            kind=req.kind,
            situation=req.situation,
            # scores that match the logged choice: the final rung's, else the cheap rung's
            options=normalise(
                final_verdict.options
                or (cheap_verdict.options if cheap_verdict is not None and not charge_failed else [])
                or req.options
            ),
            rung=final_verdict.rung,
            escalated_because=gate_reason,
            choice=final_verdict.choice,
            primitives=final_verdict.primitives,
            legality=final_verdict.legality,
            decider_errors=errors,
            request=req.model_dump(),
            intent=final_verdict.intent.model_dump() if final_verdict.intent else None,
        )
        return final_verdict.model_copy(update={"decision_id": self.log.record(decision)})
