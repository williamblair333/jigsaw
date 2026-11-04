# Jigsaw: product brief

## Core job

A developer building AI players for a strategy game gets decisions made by cheap algorithms first,
with a language model asked only when a decision is close, risky, new or involves a person, and
every decision recorded so the expensive calls can be counted and turned into rules.

## Users

- **Bill, through Parley** (the MTW2 game pack): the first and, for now, only real user. Parley
  pins a Jigsaw tag and supplies the adapter, the deciders and the model calls.
- **Later, game-AI hobbyists and modders** writing a pack for another turn-based game. They know
  Python, have uv (which fetches Python 3.11+ if needed), and know their game. They don't know Jigsaw's
  ladder or gate, and may have no API key at hand.

The engine assumes no game, no model provider and no network. A pack brings those.

## Success

- **Time to first result: under 120 seconds** from `git clone` to the quickstart printing two
  logged decisions, one of them escalated, on a clean machine with Python.
- **Every decision is logged.** `Ladder.decide` with a log writes exactly one row per call,
  including the rung, the choice and why it escalated.
- **Most decisions stay cheap.** In a Parley campaign, `DecisionLog.rung_counts` shows rungs 0–4
  taking the large majority of decisions. The target ratio is set once the log has a campaign's data.
- **Every escalation names its reason** (close call, high stakes, novelty, human, cadence), so the
  gate can later learn from agreement rates.
- **No game names in the engine.** `src/jigsaw` stays free of MTW2 or any other game.

## First-run path

1. `git clone https://github.com/williamblair333/jigsaw && cd jigsaw`
2. `uv sync`
3. `uv run examples/quickstart.py`

It prints a clear-win decision kept at rung 2, a close call escalated to rung 7 (a stub stands in
for the model, so no key is needed), and the per-rung counts read back from the SQLite log.

## Non-goals

- **Real-time games.** Turn-based only for v1.
- **A model client.** Jigsaw doesn't call any model provider itself. Rungs 5–7 are deciders the
  pack writes, so keys, prompts and providers stay with the pack.
- **Game knowledge in the engine.** Rules, actions and inventories for a game live in its pack.
- **A hosted service or UI.** It's a Python library; the log is a SQLite file you query.
- **Training models.** Distillation turns logged decisions into rules, not into fine-tunes.

## UI principles

- **Library first.** The engine never prints and never prompts. Output is the returned
  `Verdict` and the log row.
- **Every verdict explains itself.** `Verdict.reason` always says which rung decided and why it
  climbed. "No decider answered" is an explicit verdict that hands the decision back to the game's
  own AI, not a silent `None`.
- **Bad input fails loudly and early.** Models are pydantic; an out-of-range rung or a missing
  field raises a validation error at construction, not halfway through a turn.
- **Nothing leaves the machine** unless a pack's decider sends it.

```yaml
verify:
  image: ghcr.io/astral-sh/uv:python3.12-bookworm-slim
  network: required
  install:
    - uv sync
  run: uv run examples/quickstart.py /tmp/jigsaw/decisions.db
  expect:
    - stdout_contains: "Final: farm, decided at rung 2"
    - stdout_contains: "#2 turn 2 recruit: archers at rung 7 (close call"
    - stdout_contains: "1 of 2 decisions needed a model"
    - file: /tmp/jigsaw/decisions.db
    - exit_code: 0
  time_target_seconds: 120
```
