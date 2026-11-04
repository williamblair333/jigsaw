"""Quickstart: two decisions through the ladder, logged to SQLite. Offline, no API keys.

A rung-2 utility scorer answers both. The first is a clear win and stays at rung 2. The second
is a close call, so the gate escalates it to rung 7, played here by a stub instead of a real
model. Run: uv run examples/quickstart.py [LOG_PATH]
"""

from __future__ import annotations

import sys
from pathlib import Path

from jigsaw.decision_log import DecisionLog, Option
from jigsaw.ladder import Gate, Ladder, Request, Verdict


class BestScore:
    """Rung 2: pick the highest-scoring option."""

    rung = 2

    def decide(self, req: Request) -> Verdict | None:
        scored = [o for o in req.options if o.score is not None]
        if not scored:
            return None
        best = max(scored, key=lambda o: o.score)
        return Verdict(choice=best.name, rung=self.rung, reason=f"highest score {best.score:.2f}")


class StubModel:
    """Rung 7 stand-in for a strong model, so the example runs without credentials."""

    rung = 7

    def decide(self, req: Request) -> Verdict | None:
        return Verdict(choice=req.options[-1].name, rung=self.rung, reason="stub model reviewed it")


def main(log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with DecisionLog(log_path) as log:
        ladder = Ladder([BestScore(), StubModel()], Gate(), log)
        requests = [
            Request(game="demo", turn=1, actor="north", kind="build", situation="spare gold",
                    options=[Option(name="farm", score=0.9), Option(name="walls", score=0.3)]),
            Request(game="demo", turn=2, actor="north", kind="recruit", situation="border raid",
                    options=[Option(name="spearmen", score=0.62), Option(name="archers", score=0.58)]),
        ]
        for req in requests:
            v = ladder.decide(req)
            print(f"turn {req.turn} {req.kind}: {v.choice} at rung {v.rung} ({v.reason})")
        counts = log.rung_counts("demo")
    print(f"logged {sum(counts.values())} decisions to {log_path}; per rung: {dict(sorted(counts.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/jigsaw/decisions.db")))
