"""A failed log write never discards the verdict; it is counted and surfaced to the caller."""

import logging
from pathlib import Path
import sqlite3

import pytest

from jigsaw.decision_log import Decision, DecisionLog
from jigsaw.ladder import Gate, GateConfig, Ladder, Request, Verdict


class Answers:
    rung = 2

    def decide(self, req: Request) -> Verdict | None:
        return Verdict(choice="farm", rung=2, reason="rule")


class FailingLog(DecisionLog):
    """A real log whose writes fail, as on a full disk or a locked file."""

    def record(self, d: Decision) -> int:
        raise sqlite3.OperationalError("database or disk is full")


def _req(turn: int = 3) -> Request:
    return Request(game="g", turn=turn, actor="a", kind="build", situation="s")


def _ladder(log: DecisionLog) -> Ladder:
    return Ladder([Answers()], Gate(GateConfig(cadence=0)), log)


def test_failed_write_keeps_the_verdict(tmp_path: Path) -> None:
    ladder = _ladder(FailingLog(tmp_path / "d.db"))

    v = ladder.decide(_req())

    assert (v.choice, v.rung) == ("farm", 2)
    assert v.decision_id is None
    assert v.log_error == "OperationalError: database or disk is full"


def test_failures_are_counted(tmp_path: Path) -> None:
    ladder = _ladder(FailingLog(tmp_path / "d.db"))
    for turn in range(3):
        ladder.decide(_req(turn))
    assert ladder.log_failures == 3


def test_failure_is_logged_as_a_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="jigsaw"):
        _ladder(FailingLog(tmp_path / "d.db")).decide(_req())
    assert any("not logged" in r.getMessage() for r in caplog.records)


def test_closed_log_is_contained_too(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    log.close()

    v = _ladder(log).decide(_req())

    assert v.choice == "farm" and v.decision_id is None
    assert v.log_error.startswith("ProgrammingError")


def test_successful_write_has_no_error(tmp_path: Path) -> None:
    ladder = _ladder(DecisionLog(tmp_path / "d.db"))
    v = ladder.decide(_req())
    assert v.decision_id is not None and v.log_error is None
    assert ladder.log_failures == 0
