"""Each log row keeps the whole Request; logged rows replay through a candidate gate or ladder."""

from pathlib import Path
import sqlite3
import sys
import textwrap

import pytest

from jigsaw.cli import main
from jigsaw.decision_log import SCHEMA_VERSION, Decision, DecisionLog, Option
from jigsaw.ladder import Gate, GateConfig, Ladder, Request, Verdict
from jigsaw.replay import replay_gate, replay_ladder


class Scorer:
    """Rung 2: picks the top-scored option."""

    rung = 2

    def decide(self, req: Request) -> Verdict | None:
        scored = [o for o in req.options if o.score is not None]
        if not scored:
            return None
        best = max(scored, key=lambda o: o.score)
        return Verdict(choice=best.name, rung=2, reason="top score")


class Model:
    """Rung 7: always picks a fixed option, and counts its calls."""

    rung = 7

    def __init__(self, choice: str) -> None:
        self.choice = choice
        self.calls = 0

    def decide(self, req: Request) -> Verdict | None:
        self.calls += 1
        return Verdict(choice=self.choice, rung=7, reason="model")


def _req(turn: int, a: float, b: float, **kw) -> Request:
    return Request(game="g", turn=turn, actor="venice", kind="recruit", situation="s",
                   options=[Option(name="spears", score=a), Option(name="archers", score=b)], **kw)


def _campaign(path: Path, model_choice: str = "archers") -> DecisionLog:
    """Three logged decisions: one quiet, one close call, one high-stakes."""
    log = DecisionLog(path)
    ladder = Ladder([Scorer(), Model(model_choice)], Gate(GateConfig(cadence=0)), log)
    ladder.decide(_req(1, 0.9, 0.2))               # gap 0.70: quiet, spears
    ladder.decide(_req(2, 0.60, 0.55))             # gap 0.05: close call, model says archers
    ladder.decide(_req(3, 0.9, 0.1, stakes=0.8))   # high stakes, model says archers
    return log


# ---------------------------------------------------------------------------
# the whole request is stored
# ---------------------------------------------------------------------------


def test_row_keeps_the_whole_request(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    req = _req(4, 120.0, 80.0, stakes=0.3, human=True, context={"region": "Milan", "gold": 900})
    v = Ladder([Scorer()], Gate(), log).decide(req)

    stored = log.get(v.decision_id).request
    assert Request.model_validate(stored) == req   # raw scores kept, not the normalised ones


def test_context_that_is_not_json_is_stored_as_text(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    req = _req(1, 0.9, 0.1, context={"when": object()})
    v = Ladder([Scorer()], Gate(), log).decide(req)

    assert log.get(v.decision_id).request["context"]["when"].startswith("<object object")


def test_schema_3_adds_request_column_to_a_v2_file(tmp_path: Path) -> None:
    path = tmp_path / "v2.db"
    DecisionLog(path).close()
    with sqlite3.connect(path) as conn:   # make it look like a v0.2.0 file
        conn.execute("ALTER TABLE decisions DROP COLUMN request")
        conn.execute("PRAGMA user_version = 2")
        conn.execute(
            "INSERT INTO decisions (game, turn, actor, kind, situation, options, rung, "
            "escalated_because, choice, primitives, legality, created_at) "
            "VALUES ('g', 1, 'a', 'k', 's', '[]', 2, '', 'x', '[]', '[]', 'then')"
        )
    with DecisionLog(path) as log:
        assert log.get(1).request is None
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 3


# ---------------------------------------------------------------------------
# replay through a candidate gate: no deciders run
# ---------------------------------------------------------------------------


def test_replay_gate_with_a_wider_margin_escalates_more(tmp_path: Path) -> None:
    log = _campaign(tmp_path / "d.db")

    report = replay_gate(log, Gate(GateConfig(margin=0.9, cadence=0)))

    assert [r.logged_escalated != "" for r in report.rows] == [True, True, False]  # newest first
    assert all(r.new_escalated for r in report.rows)
    assert report.escalated_before == 2 and report.escalated_now == 3


def test_replay_gate_that_stops_escalating_shows_what_would_change(tmp_path: Path) -> None:
    log = _campaign(tmp_path / "d.db")

    report = replay_gate(log, Gate(GateConfig(margin=0.0, stakes_threshold=1.1, cadence=0)))

    assert report.escalated_now == 0
    # the close call (turn 2): the model chose archers, the cheap rung spears
    turn2 = next(r for r in report.rows if r.turn == 2)
    assert turn2.new_choice == "spears" and turn2.changed_choice
    assert report.changed_choices == 2   # turn 2 and turn 3 both flip from archers to spears


def test_replay_gate_counts_quiet_rows_where_model_agreed_as_unchanged(tmp_path: Path) -> None:
    log = _campaign(tmp_path / "d.db", model_choice="spears")   # model agrees with the scorer

    report = replay_gate(log, Gate(GateConfig(margin=0.0, stakes_threshold=1.1, cadence=0)))

    assert report.escalated_now == 0
    assert report.changed_choices == 0


def test_replay_gate_skips_rows_without_a_stored_request(tmp_path: Path) -> None:
    log = DecisionLog(tmp_path / "d.db")
    old = log.record(Decision(game="g", turn=1, actor="a", kind="k", situation="s", rung=2, choice="x"))
    report = replay_gate(log, Gate())
    assert report.rows == [] and report.skipped == [old]


# ---------------------------------------------------------------------------
# replay through a candidate ladder
# ---------------------------------------------------------------------------


def test_replay_ladder_runs_deciders_and_never_writes_to_any_log(tmp_path: Path) -> None:
    log = _campaign(tmp_path / "d.db")
    other_log = DecisionLog(tmp_path / "candidate.db")
    model = Model("spears")
    candidate = Ladder([Scorer(), model], Gate(GateConfig(cadence=0)), other_log)

    report = replay_ladder(log, candidate)

    assert model.calls == 2
    assert report.changed_choices == 2
    assert len(log.query()) == 3 and other_log.query() == []


def test_replay_filters_by_kind(tmp_path: Path) -> None:
    log = _campaign(tmp_path / "d.db")
    assert replay_gate(log, Gate(), kind="build").rows == []
    assert len(replay_gate(log, Gate(), kind="recruit").rows) == 3


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------


def test_cli_replays_a_gate_from_settings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _campaign(tmp_path / "d.db").close()

    rc = main(["replay", str(tmp_path / "d.db"), "--gate", "margin=0.0,stakes_threshold=1.1,cadence=0"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "3 rows replayed" in out
    assert "escalated: 2 logged, 0 now" in out
    assert "choice would change: 2" in out


def test_cli_replays_a_ladder_from_a_factory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _campaign(tmp_path / "d.db").close()
    (tmp_path / "cand.py").write_text(textwrap.dedent("""
        from jigsaw.ladder import Gate, GateConfig, Ladder, Verdict

        class Always:
            rung = 2
            def decide(self, req):
                return Verdict(choice="archers", rung=2, reason="always")

        def make():
            return Ladder([Always()], Gate(GateConfig(cadence=0)))
    """))
    monkeypatch.syspath_prepend(str(tmp_path))

    rc = main(["replay", str(tmp_path / "d.db"), "--ladder", "cand:make"])

    assert rc == 0
    assert "choice would change: 1" in capsys.readouterr().out   # turn 1 was spears


def test_cli_rejects_an_unknown_gate_setting(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _campaign(tmp_path / "d.db").close()
    rc = main(["replay", str(tmp_path / "d.db"), "--gate", "marjin=0.2"])
    assert rc == 2
    assert "marjin" in capsys.readouterr().err
