"""The log runs in WAL mode, so a reader during a campaign never blocks a decision write."""

from pathlib import Path
import sqlite3
import time

from jigsaw.decision_log import Decision, DecisionLog


def _decision(turn: int) -> Decision:
    return Decision(game="g", turn=turn, actor="a", kind="k", situation="s", rung=2, choice="x")


def _journal_mode(path: Path) -> str:
    with sqlite3.connect(path) as conn:
        return conn.execute("PRAGMA journal_mode").fetchone()[0]


def test_new_log_uses_wal(tmp_path: Path) -> None:
    path = tmp_path / "d.db"
    DecisionLog(path).close()
    assert _journal_mode(path) == "wal"


def test_existing_log_is_switched_to_wal_on_open(tmp_path: Path) -> None:
    path = tmp_path / "d.db"
    DecisionLog(path).close()
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=DELETE")
    assert _journal_mode(path) == "delete"

    DecisionLog(path).close()

    assert _journal_mode(path) == "wal"


def test_open_read_transaction_does_not_block_a_write(tmp_path: Path) -> None:
    path = tmp_path / "d.db"
    log = DecisionLog(path)
    log.record(_decision(1))

    reader = sqlite3.connect(path, isolation_level=None)
    reader.execute("BEGIN")
    assert reader.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 1  # holds a read snapshot

    start = time.monotonic()
    log.record(_decision(2))
    assert time.monotonic() - start < 1   # without WAL this waits out the 30 s busy timeout

    assert reader.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 1  # its snapshot
    reader.execute("COMMIT")
    assert reader.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 2
    reader.close()
    log.close()


def test_memory_log_still_works() -> None:
    with DecisionLog(":memory:") as log:
        log.record(_decision(1))
        assert len(log.query()) == 1
