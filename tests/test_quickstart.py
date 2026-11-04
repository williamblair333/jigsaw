import importlib.util
from pathlib import Path

from jigsaw.decision_log import DecisionLog

QUICKSTART = Path(__file__).resolve().parent.parent / "examples" / "quickstart.py"


def load_quickstart():
    spec = importlib.util.spec_from_file_location("quickstart", QUICKSTART)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quickstart_logs_one_cheap_and_one_escalated_decision(tmp_path, capsys):
    db = tmp_path / "sub" / "decisions.db"
    assert load_quickstart().main(db) == 0

    out = capsys.readouterr().out
    assert "turn 1 build: farm at rung 2" in out
    assert "turn 2 recruit: archers at rung 7 (close call" in out
    assert "logged 2 decisions" in out

    with DecisionLog(db) as log:
        assert log.rung_counts("demo") == {2: 1, 7: 1}
        escalated = log.query(game="demo", rung=7)[0]
        assert escalated.escalated_because.startswith("close call")
