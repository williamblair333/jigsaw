"""A decider that raises or hangs counts as passing up; the ladder still returns a verdict."""

from pathlib import Path
import threading
import time

import pytest

from jigsaw.decision_log import DecisionLog
from jigsaw.ladder import Gate, GateConfig, Ladder, Request, Verdict


class Answers:
    def __init__(self, rung: int, choice: str) -> None:
        self.rung = rung
        self.choice = choice

    def decide(self, req: Request) -> Verdict | None:
        return Verdict(choice=self.choice, rung=self.rung, reason="ok")


class Raises:
    def __init__(self, rung: int) -> None:
        self.rung = rung

    def decide(self, req: Request) -> Verdict | None:
        raise ValueError("provider returned 500")


class Hangs:
    def __init__(self, rung: int) -> None:
        self.rung = rung
        self.release = threading.Event()

    def decide(self, req: Request) -> Verdict | None:
        self.release.wait(10)
        return Verdict(choice="late", rung=self.rung, reason="too late")


def _req(**kw) -> Request:
    base = dict(game="g", turn=3, actor="a", kind="k", situation="s")
    base.update(kw)
    return Request(**base)


def test_raising_rung_7_still_yields_the_cheap_verdict(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    ladder = Ladder([Answers(2, "raid"), Raises(7)], Gate(), log)

    v = ladder.decide(_req(stakes=0.9))

    assert v.choice == "raid" and v.rung == 2
    assert v.decider_errors == [{"rung": 7, "error": "ValueError: provider returned 500"}]
    assert "rung 7 failed" in v.reason
    assert log.get(v.decision_id).decider_errors == v.decider_errors


def test_raising_cheap_rung_passes_to_the_next_cheap_rung() -> None:
    ladder = Ladder([Raises(1), Answers(2, "farm")], Gate(GateConfig(cadence=0)))

    v = ladder.decide(_req())

    assert v.choice == "farm" and v.rung == 2
    assert v.decider_errors == [{"rung": 1, "error": "ValueError: provider returned 500"}]


def test_every_rung_raising_leaves_it_to_the_game() -> None:
    ladder = Ladder([Raises(2), Raises(7)], Gate())

    v = ladder.decide(_req())

    assert v.choice == "" and v.rung == 0
    assert [e["rung"] for e in v.decider_errors] == [2, 7]


def test_hung_decider_times_out_and_passes_up() -> None:
    hung = Hangs(7)
    ladder = Ladder([Answers(2, "raid"), hung], Gate(), decider_timeout=0.2)
    try:
        start = time.monotonic()
        v = ladder.decide(_req(stakes=0.9))
        elapsed = time.monotonic() - start
    finally:
        hung.release.set()

    assert elapsed < 2
    assert v.choice == "raid" and v.rung == 2
    assert v.decider_errors == [{"rung": 7, "error": "TimeoutError: no answer within 0.2s"}]


def test_no_timeout_runs_inline_on_the_calling_thread() -> None:
    seen: list[threading.Thread] = []

    class Records:
        rung = 2

        def decide(self, req: Request) -> Verdict | None:
            seen.append(threading.current_thread())
            return Verdict(choice="x", rung=2, reason="ok")

    Ladder([Records()], Gate(GateConfig(cadence=0))).decide(_req())

    assert seen == [threading.current_thread()]


def test_clean_run_has_no_errors(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    v = Ladder([Answers(2, "farm")], Gate(GateConfig(cadence=0)), log).decide(_req())

    assert v.decider_errors == []
    assert log.get(v.decision_id).decider_errors == []


def test_keyboard_interrupt_is_not_swallowed() -> None:
    class Interrupts:
        rung = 2

        def decide(self, req: Request) -> Verdict | None:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        Ladder([Interrupts()], Gate()).decide(_req())
