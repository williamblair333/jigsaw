"""Tests for Jigsaw decision log."""

from pathlib import Path
import pytest
from pydantic import ValidationError

from jigsaw.decision_log import Decision, DecisionLog, Option


def test_record_and_get_round_trip(tmp_path: Path) -> None:
    """Verify that recording a decision and retrieving it round-trips every field."""
    db_path = tmp_path / "test.db"
    log = DecisionLog(db_path)
    decision = Decision(
        game="mtw2",
        turn=5,
        actor="venice",
        kind="diplomacy",
        situation="Milan seeks ceasefire and offers 500 gold",
        options=[
            Option(name="accept", score=0.85, note="profitable"),
            Option(name="reject", score=0.15, note="want settlement"),
        ],
        rung=6,
        escalated_because="treaty margin below threshold",
        choice="accept",
        primitives=[{"action": "diplomacy_accept", "target": "Milan"}],
        legality=[{"valid": True, "reason": "diplomat present"}],
        outcome="peace_held",
        outcome_turn=8,
        created_at="2026-10-26T12:00:00+00:00",
    )
    assigned_id = log.record(decision)
    assert assigned_id == decision.id
    assert assigned_id == 1

    fetched = log.get(assigned_id)
    assert fetched == decision
    assert fetched.id == 1
    assert fetched.game == "mtw2"
    assert fetched.turn == 5
    assert fetched.actor == "venice"
    assert fetched.kind == "diplomacy"
    assert fetched.situation == "Milan seeks ceasefire and offers 500 gold"
    assert len(fetched.options) == 2
    assert fetched.options[0].name == "accept"
    assert fetched.options[0].score == 0.85
    assert fetched.options[0].note == "profitable"
    assert fetched.options[1].name == "reject"
    assert fetched.options[1].score == 0.15
    assert fetched.options[1].note == "want settlement"
    assert fetched.rung == 6
    assert fetched.escalated_because == "treaty margin below threshold"
    assert fetched.choice == "accept"
    assert fetched.primitives == [{"action": "diplomacy_accept", "target": "Milan"}]
    assert fetched.legality == [{"valid": True, "reason": "diplomat present"}]
    assert fetched.outcome == "peace_held"
    assert fetched.outcome_turn == 8
    assert fetched.created_at == "2026-10-26T12:00:00+00:00"
    log.close()


def test_set_outcome(tmp_path: Path) -> None:
    """Verify that set_outcome updates outcome fields and commits immediately."""
    db_path = tmp_path / "test.db"
    with DecisionLog(db_path) as log:
        d = Decision(
            game="mtw2",
            turn=10,
            actor="england",
            kind="siege",
            situation="assault caen",
            choice="assault",
            rung=3,
        )
        d_id = log.record(d)
        initial = log.get(d_id)
        assert initial.outcome is None
        assert initial.outcome_turn is None

        log.set_outcome(d_id, "settlement_captured", 12)
        updated = log.get(d_id)
        assert updated.outcome == "settlement_captured"
        assert updated.outcome_turn == 12

        with pytest.raises(KeyError):
            log.set_outcome(999, "failed", 13)


def test_query_filters(tmp_path: Path) -> None:
    """Verify each query filter individually, in combination, and newest-first ordering."""
    db_path = tmp_path / "test.db"
    with DecisionLog(db_path) as log:
        d1 = Decision(
            game="mtw2",
            turn=1,
            actor="england",
            kind="build",
            situation="build barracks",
            choice="barracks",
            rung=2,
        )
        d2 = Decision(
            game="mtw2",
            turn=3,
            actor="france",
            kind="build",
            situation="build farm",
            choice="farm",
            rung=2,
        )
        d3 = Decision(
            game="mtw2",
            turn=5,
            actor="england",
            kind="war",
            situation="siege caen",
            choice="siege",
            rung=3,
        )
        d4 = Decision(
            game="civ5",
            turn=10,
            actor="rome",
            kind="war",
            situation="declare war",
            choice="war",
            rung=7,
        )

        id1 = log.record(d1)
        id2 = log.record(d2)
        id3 = log.record(d3)
        id4 = log.record(d4)

        # Unfiltered returns all newest first
        all_results = log.query()
        assert [r.id for r in all_results] == [id4, id3, id2, id1]

        # Filter by game
        mtw_results = log.query(game="mtw2")
        assert [r.id for r in mtw_results] == [id3, id2, id1]
        civ_results = log.query(game="civ5")
        assert [r.id for r in civ_results] == [id4]

        # Filter by actor
        england_results = log.query(actor="england")
        assert [r.id for r in england_results] == [id3, id1]
        france_results = log.query(actor="france")
        assert [r.id for r in france_results] == [id2]

        # Filter by kind
        war_results = log.query(kind="war")
        assert [r.id for r in war_results] == [id4, id3]
        build_results = log.query(kind="build")
        assert [r.id for r in build_results] == [id2, id1]

        # Filter by rung
        rung2_results = log.query(rung=2)
        assert [r.id for r in rung2_results] == [id2, id1]
        rung7_results = log.query(rung=7)
        assert [r.id for r in rung7_results] == [id4]

        # Filter by since_turn
        since3_results = log.query(since_turn=3)
        assert [r.id for r in since3_results] == [id4, id3, id2]
        since5_results = log.query(since_turn=5)
        assert [r.id for r in since5_results] == [id4, id3]
        since11_results = log.query(since_turn=11)
        assert since11_results == []

        # Combined filters
        combined = log.query(game="mtw2", actor="england", kind="war")
        assert [r.id for r in combined] == [id3]

        combined_empty = log.query(game="mtw2", actor="rome")
        assert combined_empty == []


def test_rung_counts(tmp_path: Path) -> None:
    """Verify rung_counts aggregation by game."""
    db_path = tmp_path / "test.db"
    with DecisionLog(db_path) as log:
        log.record(Decision(game="mtw2", turn=1, actor="a", kind="k", situation="s", choice="c", rung=1))
        log.record(Decision(game="mtw2", turn=2, actor="a", kind="k", situation="s", choice="c", rung=2))
        log.record(Decision(game="mtw2", turn=3, actor="a", kind="k", situation="s", choice="c", rung=2))
        log.record(Decision(game="mtw2", turn=4, actor="a", kind="k", situation="s", choice="c", rung=7))
        log.record(Decision(game="civ5", turn=1, actor="b", kind="k", situation="s", choice="c", rung=6))

        assert log.rung_counts("mtw2") == {1: 1, 2: 2, 7: 1}
        assert log.rung_counts("civ5") == {6: 1}
        assert log.rung_counts("unknown") == {}


def test_rung_outside_range_rejected() -> None:
    """Verify that rung values strictly outside 0..7 are rejected."""
    with pytest.raises(ValidationError):
        Decision(game="mtw2", turn=1, actor="a", kind="k", situation="s", choice="c", rung=-1)

    with pytest.raises(ValidationError):
        Decision(game="mtw2", turn=1, actor="a", kind="k", situation="s", choice="c", rung=8)

    # 0 and 7 boundaries are accepted
    d0 = Decision(game="mtw2", turn=1, actor="a", kind="k", situation="s", choice="c", rung=0)
    assert d0.rung == 0
    d7 = Decision(game="mtw2", turn=1, actor="a", kind="k", situation="s", choice="c", rung=7)
    assert d7.rung == 7


def test_file_survives_close_and_reopen(tmp_path: Path) -> None:
    """Verify that decisions and updates persist across close and reopen."""
    db_path = tmp_path / "persistent.db"
    d = Decision(
        game="mtw2",
        turn=4,
        actor="france",
        kind="build",
        situation="Paris build choice",
        options=[Option(name="roads", score=0.9, note="mobility")],
        rung=2,
        choice="roads",
    )

    with DecisionLog(db_path) as log1:
        d_id = log1.record(d)
        log1.set_outcome(d_id, "completed", 6)

    # Reopen database in another DecisionLog instance
    with DecisionLog(db_path) as log2:
        retrieved = log2.get(d_id)
        assert retrieved.id == d_id
        assert retrieved.game == "mtw2"
        assert retrieved.choice == "roads"
        assert retrieved.outcome == "completed"
        assert retrieved.outcome_turn == 6
        assert len(retrieved.options) == 1
        assert retrieved.options[0].name == "roads"

        # Record another decision after reopening
        d2 = Decision(
            game="mtw2",
            turn=7,
            actor="france",
            kind="recruit",
            situation="Paris recruit",
            choice="militia",
            rung=1,
        )
        d2_id = log2.record(d2)
        assert d2_id == d_id + 1
        assert len(log2.query(game="mtw2")) == 2


def test_get_nonexistent_raises(tmp_path: Path) -> None:
    """Verify that get on nonexistent id raises KeyError."""
    with DecisionLog(tmp_path / "test.db") as log:
        with pytest.raises(KeyError):
            log.get(999)
