"""skip-lot-gate, a STANDARDS idea: acceptance sampling for escalations.

From manufacturing acceptance sampling (ANSI/ASQ Z1.4 switching rules). A kind of decision
where the model keeps agreeing with the cheap rung doesn't need asking every time. After
`streak` agreements in a row for a kind, the gate escalates that kind only on a random
`sample` of the close calls and cadence reviews it would have escalated. One disagreement
puts the kind back to "always".

Human and high-stakes escalations are never skipped, and neither is novelty (no cheap answer).

Streaks are kept per (game, kind), and only skippable escalations (close calls, cadence
reviews) feed them. The ladder tells the gate each such agreement or disagreement through
observe(), and so does replay_gate when it replays a log. A logged row whose answer the budget
couldn't pay for shows rung 0, so a replay observes it as nothing; the live gate did observe it. So `jigsaw.replay.replay_gate(log, SkipLotGate(...))`
runs the idea's test offline: how many strong-rung calls it saves, and how many choices it
would have changed.
"""

from collections import defaultdict
import random
import threading

from jigsaw.ladder import Gate, GateConfig, Request, Verdict

# the reasons that are never skipped, as Gate.check writes them
_NEVER_SKIP = ("human", "high stakes", "novelty")


class SkipLotGate(Gate):
    def __init__(
        self,
        config: GateConfig | None = None,
        streak: int = 20,
        sample: float = 0.1,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(config)
        if streak < 1 or not 0.0 <= sample <= 1.0:
            raise ValueError("streak must be >= 1 and sample in 0..1")
        self.streak_needed = streak
        self.sample = sample
        self._rng = rng if rng is not None else random.Random()
        self._lock = threading.Lock()
        # agreement streaks and skipped escalations, per (game, kind)
        self._streak: dict[tuple[str, str], int] = defaultdict(int)
        self.skipped: dict[tuple[str, str], int] = defaultdict(int)

    def streak(self, game: str, kind: str) -> int:
        with self._lock:
            return self._streak[(game, kind)]

    def observe(self, req: Request, agreed: bool, reason: str) -> None:
        """An escalated decision finished: did the strong rung agree with the cheap one?

        Only escalations this gate could have skipped count. A high-stakes or human call
        that agreed says nothing about whether routine close calls of that kind need asking.
        """
        if not reason or reason.startswith(_NEVER_SKIP):
            return
        with self._lock:
            key = (req.game, req.kind)
            self._streak[key] = self._streak[key] + 1 if agreed else 0

    def check(self, req: Request, verdict: Verdict | None) -> str:
        reason = super().check(req, verdict)
        if not reason or reason.startswith(_NEVER_SKIP):
            return reason
        key = (req.game, req.kind)
        with self._lock:
            if self._streak[key] < self.streak_needed:
                return reason
            if self._rng.random() < self.sample:
                return f"{reason} (skip-lot sample)"
            self.skipped[key] += 1
            return ""
