"""Per game and kind: how often the escalated rung agreed with the cheap one."""

from pathlib import Path

import pytest

from jigsaw.cli import main
from jigsaw.decision_log import Decision, DecisionLog
from jigsaw.report import concordance


def _row(log: DecisionLog, kind: str, choice: str, rung: int, cheap: str | None = None,
         cheap_rung: int | None = None, escalated: str = "", game: str = "g") -> None:
    log.record(Decision(game=game, turn=1, actor="a", kind=kind, situation="s", rung=rung,
                        choice=choice, escalated_because=escalated,
                        cheap_choice=cheap, cheap_rung=cheap_rung))


@pytest.fixture
def log(tmp_path: Path) -> DecisionLog:
    log = DecisionLog(tmp_path / "d.db")
    # recruit: 4 escalations a model answered, 3 agreed with the cheap rung; 1 quiet row
    for choice in ["spears", "spears", "spears", "archers"]:
        _row(log, "recruit", choice, 7, cheap="spears", cheap_rung=2, escalated="close call")
    _row(log, "recruit", "spears", 2)
    # build: escalated, but no higher rung answered, so the cheap answer stood: not comparable
    _row(log, "build", "farm", 2, cheap="farm", cheap_rung=2, escalated="high stakes (0.90)")
    # build: escalated with no cheap answer (novelty): not comparable
    _row(log, "build", "mine", 7, escalated="novelty: no rule matched")
    # another game, so per-game grouping is visible
    _row(log, "recruit", "archers", 7, cheap="spears", cheap_rung=2, escalated="close call", game="h")
    return log


def test_counts_per_game_and_kind(log: DecisionLog) -> None:
    rows = {(r.game, r.kind): r for r in concordance(log)}

    rec = rows[("g", "recruit")]
    assert (rec.decisions, rec.escalated, rec.compared, rec.agreed) == (5, 4, 4, 3)
    assert rec.agreement == pytest.approx(0.75)

    build = rows[("g", "build")]
    assert (build.decisions, build.escalated, build.compared, build.agreed) == (2, 2, 0, 0)
    assert build.agreement is None

    assert rows[("h", "recruit")].agreement == 0.0


def test_filter_by_game(log: DecisionLog) -> None:
    assert {r.game for r in concordance(log, game="h")} == {"h"}


def test_rows_sorted_by_game_then_kind(log: DecisionLog) -> None:
    assert [(r.game, r.kind) for r in concordance(log)] == [("g", "build"), ("g", "recruit"), ("h", "recruit")]


def test_cli_prints_a_table(log: DecisionLog, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log.close()
    rc = main(["concordance", str(tmp_path / "d.db"), "--game", "g"])
    out = capsys.readouterr().out
    assert rc == 0
    lines = out.splitlines()
    assert lines[0].split() == ["game", "kind", "decisions", "escalated", "compared", "agreed", "agreement"]
    assert lines[1].split() == ["g", "build", "2", "2", "0", "0", "-"]
    assert lines[2].split() == ["g", "recruit", "5", "4", "4", "3", "75%"]


def test_cli_refuses_a_missing_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["concordance", str(tmp_path / "nope.db")])
    assert rc == 2
    assert "no such log" in capsys.readouterr().err
