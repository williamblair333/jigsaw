"""The `jigsaw` command line: replay and concordance."""

import argparse
import importlib
from pathlib import Path
import sqlite3
import sys
from typing import Any

from jigsaw.decision_log import DecisionLog
from jigsaw.ladder import Gate, GateConfig, Ladder
from jigsaw.replay import replay_gate, replay_ladder
from jigsaw.report import concordance, concordance_table


def _gate_config(text: str) -> GateConfig:
    """Parse "margin=0.2,cadence=0" into a GateConfig. Unset fields keep their defaults."""
    values: dict[str, Any] = {}
    for pair in filter(None, (p.strip() for p in text.split(","))):
        key, sep, value = pair.partition("=")
        if not sep:
            raise ValueError(f"expected name=value, got {pair!r}")
        if key not in GateConfig.model_fields:
            known = ", ".join(GateConfig.model_fields)
            raise ValueError(f"unknown gate setting {key!r} (known: {known})")
        values[key] = value
    return GateConfig.model_validate(values)


def _ladder(spec: str) -> Ladder:
    """Load "package.module:factory" and call factory() to get a Ladder."""
    module_name, sep, attr = spec.partition(":")
    if not sep:
        raise ValueError(f"expected module:factory, got {spec!r}")
    factory = getattr(importlib.import_module(module_name), attr)
    try:
        ladder = factory()
    except Exception as exc:
        raise ValueError(f"{spec} raised {type(exc).__name__}: {exc}") from exc
    if not isinstance(ladder, Ladder):
        raise ValueError(f"{spec} returned {type(ladder).__name__}, not a Ladder")
    return ladder


def _open(path: str) -> DecisionLog | None:
    """Open an existing log, or print why not and return None. Never creates a file."""
    if not Path(path).is_file():
        print(f"jigsaw: no such log: {path}", file=sys.stderr)
        return None
    try:
        return DecisionLog(path)
    except (RuntimeError, sqlite3.Error) as exc:
        print(f"jigsaw: can't open {path}: {exc}", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jigsaw")
    commands = parser.add_subparsers(dest="command", required=True)
    rp = commands.add_parser(
        "replay",
        help="rerun logged decisions through a candidate gate or ladder",
        description=(
            "Rerun logged decisions offline. --gate tries new gate settings and runs no "
            "deciders, so it costs nothing. --ladder runs your candidate ladder's deciders for "
            "real: model rungs make real calls. Replay records no decisions, but opening a log "
            "from an older Jigsaw upgrades its layout, as any Jigsaw does."
        ),
    )
    rp.add_argument("log", help="path to a decision log (.db)")
    which = rp.add_mutually_exclusive_group(required=True)
    which.add_argument("--gate", metavar="SETTINGS",
                       help="gate settings, e.g. margin=0.2,stakes_threshold=0.6,cadence=0")
    which.add_argument("--ladder", metavar="MODULE:FACTORY",
                       help="a function that returns the candidate Ladder")
    rp.add_argument("--game")
    rp.add_argument("--actor")
    rp.add_argument("--kind")
    rp.add_argument("--since-turn", type=int)
    cp = commands.add_parser(
        "concordance",
        help="per game and kind: how often the escalated rung agreed with the cheap one",
        description=(
            "Per game and kind of decision: how many escalated, how many a model rung answered "
            "after a cheap rung had (compared), and how often the two agreed. Reads only, but "
            "opening a log from an older Jigsaw upgrades its layout, as any Jigsaw does."
        ),
    )
    cp.add_argument("log", help="path to a decision log (.db)")
    cp.add_argument("--game")
    args = parser.parse_args(argv)

    if args.command == "concordance":
        log = _open(args.log)
        if log is None:
            return 2
        with log:
            print(concordance_table(concordance(log, game=args.game)))
        return 0

    filters = {k: v for k, v in
               {"game": args.game, "actor": args.actor, "kind": args.kind,
                "since_turn": args.since_turn}.items() if v is not None}
    try:
        gate = Gate(_gate_config(args.gate)) if args.gate is not None else None
        ladder = _ladder(args.ladder) if args.ladder is not None else None
    except (ValueError, ImportError, AttributeError) as exc:
        print(f"jigsaw replay: {exc}", file=sys.stderr)
        return 2

    log = _open(args.log)
    if log is None:
        return 2
    with log:
        if gate is not None:
            report = replay_gate(log, gate, **filters)
        else:
            assert ladder is not None  # argparse requires exactly one of --gate and --ladder
            report = replay_ladder(log, ladder, **filters)
    print(report.summary())
    if not report.rows and report.skipped:
        print("jigsaw replay: no row could be replayed; every matching row was logged before "
              "Jigsaw stored requests (v0.3.0)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
