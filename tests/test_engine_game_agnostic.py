"""The engine names no game and no game pack. Anything game-specific belongs in its pack."""

from pathlib import Path
import re

SRC = Path(__file__).resolve().parents[1] / "src" / "jigsaw"

# Games and packs Jigsaw is used with. Add a name here when a new pack appears.
FORBIDDEN = re.compile(r"parley|mtw2|m2tw|medieval|total\s*war", re.IGNORECASE)


def test_engine_names_no_game_or_pack() -> None:
    hits = [
        f"{path.relative_to(SRC.parent)}:{n}: {line.strip()}"
        for path in sorted(SRC.rglob("*.py"))
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if FORBIDDEN.search(line)
    ]
    assert hits == [], "engine code names a game or pack:\n" + "\n".join(hits)


def test_the_check_sees_every_engine_module() -> None:
    names = {p.name for p in SRC.rglob("*.py")}
    assert {"ladder.py", "decision_log.py", "replay.py", "report.py", "cli.py"} <= names
