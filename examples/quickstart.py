"""Quickstart: watch Jigsaw make two decisions, then read them back from the log.

Offline and needs no API key. A stub stands in for the language model.

Run: uv run examples/quickstart.py [LOG_PATH]
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from jigsaw import DecisionLog, Gate, Ladder, Option, Request, Verdict


class BestScore:
    """Rung 2, a cheap scorer: pick the option with the highest score. No model involved."""

    rung = 2

    def decide(self, req: Request) -> Verdict | None:
        scored = [o for o in req.options if o.score is not None]
        if not scored:
            return None  # can't decide: pass the decision up
        best = max(scored, key=lambda o: o.score)
        return Verdict(choice=best.name, rung=self.rung, reason=f"highest score ({best.score:.2f})")


class StubModel:
    """Rung 7, standing in for a strong language model. Its answer is canned for the demo."""

    rung = 7

    def decide(self, req: Request) -> Verdict | None:
        return Verdict(choice="archers", rung=self.rung,
                       reason="raiders are light horse; archers thin them before they reach the walls")


def explain(req: Request, verdict: Verdict, gate: Gate) -> None:
    options = ", ".join(f"{o.name} {o.score:.2f}" for o in req.options)
    print(f"Turn {req.turn}: {req.actor} must choose what to {req.kind}. Options: {options}.")
    cheap = BestScore().decide(req)
    print(f"  The cheap scorer (rung 2) picks {cheap.choice}.")
    reason = gate.check(req, cheap)
    if not reason:
        print("  The gate sees no reason to ask a model, so that's the answer. Cost: no model call.")
    else:
        scores = sorted((o.score for o in req.options), reverse=True)
        print(f"  The gate escalates: {reason}. The top two scores are {scores[0] - scores[1]:.2f} apart,")
        print(f"  under the gate's {gate.config.margin:.2f} margin, so the scorer's pick is close to a coin flip.")
        print(f"  The model (rung {verdict.rung}) picks {verdict.choice}.")
    print(f"  Final: {verdict.choice}, decided at rung {verdict.rung}. Logged as decision #{verdict.decision_id}.\n")


def main(log_path: Path) -> int:
    gate = Gate()
    with DecisionLog(log_path) as log:
        ladder = Ladder([BestScore(), StubModel()], gate, log)
        requests = [
            Request(game="demo", turn=1, actor="the northern kingdom", kind="build",
                    situation="spare gold, no threats",
                    options=[Option(name="farm", score=0.90), Option(name="walls", score=0.30)]),
            Request(game="demo", turn=2, actor="the northern kingdom", kind="recruit",
                    situation="raiders on the border",
                    options=[Option(name="spearmen", score=0.62), Option(name="archers", score=0.58)]),
        ]
        for req in requests:
            explain(req, ladder.decide(req), gate)

        counts = log.rung_counts("demo")
        print(f"The log ({log_path}) now holds {sum(counts.values())} decisions:")
        for d in reversed(log.query(game="demo")):
            why = d.escalated_because or "no escalation"
            print(f"  #{d.id} turn {d.turn} {d.kind}: {d.choice} at rung {d.rung} ({why})")
        model_calls = sum(n for rung, n in counts.items() if rung >= gate.config.escalate_rung)
        print(f"{model_calls} of {sum(counts.values())} decisions needed a model. "
              "In a real campaign the log shows which kinds of decision keep needing one.")
    return 0


if __name__ == "__main__":
    # With no path, each run starts a fresh log; a path you pass is appended to.
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="jigsaw-")) / "decisions.db"
    sys.exit(main(path))
