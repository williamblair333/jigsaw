"""The `jigsaw` command line. One command so far: replay."""

import argparse
import importlib
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
    ladder = getattr(importlib.import_module(module_name), attr)()
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
            "real: model rungs make real calls. Nothing is written to any log."
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

    with DecisionLog(args.log) as log:
        report = replay_gate(log, gate, **filters) if gate else replay_ladder(log, ladder, **filters)
    print(report.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
