"""The `jigsaw` command line. One command so far: replay."""

import argparse
import importlib
from pathlib import Path
import sqlite3
import sys
from typing import Any

from jigsaw.decision_log import DecisionLog
from jigsaw.ladder import Gate, GateConfig, Ladder
from jigsaw.replay import replay_gate, replay_ladder


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
    args = parser.parse_args(argv)

    filters = {k: v for k, v in
               {"game": args.game, "actor": args.actor, "kind": args.kind,
                "since_turn": args.since_turn}.items() if v is not None}
    try:
        gate = Gate(_gate_config(args.gate)) if args.gate is not None else None
        ladder = _ladder(args.ladder) if args.ladder is not None else None
    except (ValueError, ImportError, AttributeError) as exc:
        print(f"jigsaw replay: {exc}", file=sys.stderr)
        return 2

    if not Path(args.log).is_file():
        print(f"jigsaw replay: no such log: {args.log}", file=sys.stderr)
        return 2
    try:
        log = DecisionLog(args.log)
    except (RuntimeError, sqlite3.Error) as exc:
        print(f"jigsaw replay: can't open {args.log}: {exc}", file=sys.stderr)
        return 2
    with log:
        report = replay_gate(log, gate, **filters) if gate else replay_ladder(log, ladder, **filters)
    print(report.summary())
    if not report.rows and report.skipped:
        print("jigsaw replay: no row could be replayed; every matching row was logged before "
              "Jigsaw stored requests (v0.3.0)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
