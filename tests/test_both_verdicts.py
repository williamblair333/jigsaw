"""Tests for logging the cheap verdict next to the final one, and for the log's schema version."""

from pathlib import Path
import sqlite3

import pytest

from jigsaw.decision_log import SCHEMA_VERSION, Decision, DecisionLog, Option
from jigsaw.ladder import Gate, GateConfig, Ladder, Request, Verdict

# The decisions table exactly as v0.1.0 created it. Files in the field look like this.
V1_TABLE = """
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game TEXT NOT NULL,
    turn INTEGER NOT NULL,
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    situation TEXT NOT NULL,
    options TEXT NOT NULL,
    rung INTEGER NOT NULL,
    escalated_because TEXT NOT NULL,
    choice TEXT NOT NULL,
    primitives TEXT NOT NULL,
    legality TEXT NOT NULL,
    outcome TEXT,
    outcome_turn INTEGER,
    created_at TEXT NOT NULL
)
"""


class FakeDecider:
    def __init__(self, rung: int, verdict: Verdict | None) -> None:
        self.rung = rung
        self.verdict = verdict

    def decide(self, req: Request) -> Verdict | None:
        return self.verdict


def _req(**kw) -> Request:
    base = dict(game="g", turn=3, actor="a", kind="k", situation="s")
    base.update(kw)
    return Request(**base)


def _user_version(path: Path) -> int:
    with sqlite3.connect(path) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


# ---------------------------------------------------------------------------
# both verdicts in the log
# ---------------------------------------------------------------------------


def test_escalated_row_keeps_cheap_choice_and_rung(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    cheap = FakeDecider(2, Verdict(choice="raid", rung=2, reason="rule"))
    strong = FakeDecider(7, Verdict(choice="ally", rung=7, reason="model"))
    ladder = Ladder([cheap, strong], Gate(), log)

    v = ladder.decide(_req(stakes=0.9))

    row = log.get(v.decision_id)
    assert row.choice == "ally" and row.rung == 7
    assert row.cheap_choice == "raid"
    assert row.cheap_rung == 2


def test_quiet_row_leaves_cheap_fields_empty(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    cheap = FakeDecider(2, Verdict(choice="raid", rung=2, reason="rule"))
    ladder = Ladder([cheap], Gate(GateConfig(cadence=0)), log)

    v = ladder.decide(_req())

    row = log.get(v.decision_id)
    assert row.escalated_because == ""
    assert row.cheap_choice is None
    assert row.cheap_rung is None


def test_escalation_with_no_cheap_answer_leaves_cheap_fields_empty(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    cheap = FakeDecider(2, None)
    strong = FakeDecider(7, Verdict(choice="ally", rung=7, reason="model"))
    ladder = Ladder([cheap, strong], Gate(), log)

    v = ladder.decide(_req())

    row = log.get(v.decision_id)
    assert row.escalated_because.startswith("novelty")
    assert row.cheap_choice is None
    assert row.cheap_rung is None


def test_escalation_with_no_higher_rung_records_cheap_as_both(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    cheap = FakeDecider(2, Verdict(choice="raid", rung=2, reason="rule"))
    ladder = Ladder([cheap], Gate(), log)

    v = ladder.decide(_req(stakes=0.9))

    row = log.get(v.decision_id)
    assert row.choice == "raid" and row.cheap_choice == "raid"
    assert row.rung == 2 and row.cheap_rung == 2


def test_cheap_fields_round_trip_through_query(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    log.record(
        Decision(game="g", turn=1, actor="a", kind="k", situation="s", rung=7,
                 choice="ally", cheap_choice="raid", cheap_rung=2)
    )
    (row,) = log.query(game="g")
    assert (row.cheap_choice, row.cheap_rung) == ("raid", 2)


# ---------------------------------------------------------------------------
# schema version and migration
# ---------------------------------------------------------------------------


def test_new_file_gets_current_version(tmp_path: Path) -> None:
    path = tmp_path / "d.db"
    DecisionLog(path).close()
    assert _user_version(path) == SCHEMA_VERSION == 2


def test_v1_file_migrates_forward_and_keeps_its_rows(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(V1_TABLE)
        conn.execute(
            "INSERT INTO decisions (game, turn, actor, kind, situation, options, rung, "
            "escalated_because, choice, primitives, legality, outcome, outcome_turn, created_at) "
            "VALUES ('g', 1, 'a', 'k', 's', ?, 2, '', 'raid', '[]', '[]', NULL, NULL, 'then')",
            ('[{"name": "raid", "score": 0.8, "note": ""}]',),
        )
    assert _user_version(path) == 0

    with DecisionLog(path) as log:
        old = log.get(1)
        assert old.choice == "raid"
        assert old.options == [Option(name="raid", score=0.8)]
        assert old.cheap_choice is None and old.cheap_rung is None
        new_id = log.record(
            Decision(game="g", turn=2, actor="a", kind="k", situation="s", rung=7,
                     choice="ally", cheap_choice="raid", cheap_rung=2)
        )
        assert log.get(new_id).cheap_choice == "raid"

    assert _user_version(path) == SCHEMA_VERSION


def test_reopening_a_current_file_is_a_no_op(tmp_path: Path) -> None:
    path = tmp_path / "d.db"
    with DecisionLog(path) as log:
        log.record(Decision(game="g", turn=1, actor="a", kind="k", situation="s", rung=2, choice="x"))
    with DecisionLog(path) as log:
        assert len(log.query()) == 1
    assert _user_version(path) == SCHEMA_VERSION


def test_file_from_a_newer_jigsaw_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    DecisionLog(path).close()
    with sqlite3.connect(path) as conn:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(RuntimeError, match="newer"):
        DecisionLog(path)


def test_current_file_opens_read_only(tmp_path: Path) -> None:
    """A current file needs no write lock to open, so a read-only copy can be queried."""
    path = tmp_path / "d.db"
    with DecisionLog(path) as log:
        log.record(Decision(game="g", turn=1, actor="a", kind="k", situation="s", rung=2, choice="x"))
    path.chmod(0o444)
    try:
        with DecisionLog(path) as log:
            assert [d.choice for d in log.query()] == ["x"]
    finally:
        path.chmod(0o644)
