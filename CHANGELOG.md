# Changelog

All notable changes to this project are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- The package ships `py.typed`, so a type checker reads Jigsaw's annotations in a project that
  imports it. Pyright runs in strict mode in CI on all three Pythons, and locally with
  `just typecheck`. Strict mode found 12 errors. Fixing them changed only annotations: list
  fields now name their element type, an always-true `isinstance` check went, and the CLI
  narrows an Optional (STANDARDS `typed-package`).
- `Ladder(legality=check)`: the pack's last gate before a move reaches the game. `check(request,
  verdict)` returns `None` when the verdict can be sent, or the reason it can't. It runs on
  every answer a decider gives. A refused answer counts as passing up, and so does one whose
  check raised: an unverified move is never returned. Each result goes into `verdict.legality`,
  into the log's `legality` column, and into the reason ("rung 7 illegal (…)") (STANDARDS
  `legality-before-verdict`).
- The package exports `Legality`, `SCHEMA_VERSION`, the replay types and functions, and
  `concordance`.
- The log uses SQLite's WAL mode, so a reader during a campaign (`jigsaw concordance`, a
  notebook) never blocks a decision write. Existing logs switch the first time they're opened.
  If the switch fails (a read-only file, a network filesystem), the log keeps its old mode and
  says so in a warning (STANDARDS `concurrent-readers`).
- `tests/test_engine_game_agnostic.py` fails if engine code (`src/jigsaw`) names a game or
  game pack. The one existing mention, a docstring, now reads "one thread per seat"
  (STANDARDS `engine-game-agnostic`).
- CI: `.gitea/workflows/ci.yml` runs the tests, the quickstart and `uv build` on Python 3.11,
  3.12 and 3.13 for every PR and every push to `main`. Branch protection on `main` requires all
  three to pass and blocks direct pushes (#21; STANDARDS `ci-on-every-pr`).
- `just contract [CONSUMER]` runs a consumer's test suite (default: Parley) against this
  checkout before a tag. It works in a throwaway worktree of the consumer's `main`, swaps in
  this Jigsaw, and prints where Jigsaw was installed from as proof. The consumer's own
  checkout is never touched. First run: 1596 Parley tests pass (STANDARDS
  `consumer-contract-test`).

### Changed
- A failed log write no longer loses the decision. If building or writing the row raises
  (disk full, a locked or closed file), `Ladder.decide` still returns the verdict. Its
  `decision_id` stays `None` and the new `verdict.log_error` says why. `Ladder.log_failures`
  counts these, and each one is a warning on the `jigsaw` logger (STANDARDS
  `log-write-failure-contained`).

## [0.3.0] - 2026-11-05

Logs move to schema 3 the first time v0.3.0 opens them. v0.2.0 refuses a schema-3 log, so
after upgrading, don't move a pin back to v0.2.0. v0.1.0 has no version check.

### Added
- Each log row keeps the whole request in a new `request` column: stakes, human, context and
  the raw option scores. This is schema version 3. Opening a v0.2.0 log adds the column; rows
  logged before it have no request. Context values that can't be stored as JSON are kept as text.
- `jigsaw.replay`: rerun logged decisions offline. `replay_gate(log, gate)` asks a candidate
  gate whether it would escalate each row. It runs no deciders, because the cheap answer is
  already in the log, so trying new thresholds costs nothing. `replay_ladder(log, ladder)` runs
  a candidate ladder's deciders for real (model rungs make real calls). Neither writes to a log.
- `jigsaw replay LOG --gate margin=0.2,cadence=0` or `--ladder module:factory`, with optional
  `--game`, `--actor`, `--kind`, `--since-turn`. It prints how many rows escalated before and
  now, and how many choices would change (STANDARDS `full-request-replayable`).
- `Verdict.escalated_because`: the gate's reason, or `""` when it didn't escalate.
- `jigsaw concordance LOG [--game G]` (and `jigsaw.report.concordance`): per game and kind of
  decision, how many decisions escalated, how many of those a higher rung answered after a
  cheap rung had answered ("compared"), and how often the two agreed (STANDARDS
  `gate-concordance-report`).

## [0.2.0] - 2026-11-05

Logs from v0.1.0 upgrade themselves the first time v0.2.0 opens them. v0.1.0 can still read
and write an upgraded log.

### Added
- The log keeps both answers when a decision escalates. `Decision` and the `decisions` table
  gain `cheap_choice` and `cheap_rung`: what the cheap rung picked before the gate sent the
  decision up. They stay empty when nothing escalated or no cheap rung answered. Comparing them
  with `choice` and `rung` gives the cheap-vs-model agreement rate (STANDARDS `log-both-verdicts`).
- The log file has a schema version (`SCHEMA_VERSION = 2`, kept in SQLite's `PRAGMA user_version`).
  Opening a v0.1.0 log adds the two new columns and keeps every row. A file from a newer Jigsaw is
  refused with a clear error. A file that is already current opens without a write lock, so a
  read-only copy can be queried (STANDARDS `schema-versioned`).
- A decider that fails no longer takes the decision down with it. If it raises an `Exception`,
  the ladder treats it as passing up and moves to the next rung. `Ladder(decider_timeout=...)`
  does the same for a decider that gives no answer in time. It's off by default; when it's set,
  each decider runs on its own daemon thread. Each failure appears in the verdict's `reason`,
  in a new `decider_errors` list on `Verdict` and in the log, and as a warning on the `jigsaw`
  logger. `KeyboardInterrupt` and `SystemExit` still stop the program (STANDARDS
  `decider-failure-contained`).

- `PRODUCT.md`: core job, users, success measures, first-run path, non-goals, UI principles and
  a `verify:` block. The first-run gate passes in a clean `python:3.12-slim` container.
- `STANDARDS.md`: the expert bar, 19 items ranked by impact, plus 3 ideas to test. Top gap:
  `log-both-verdicts` (the cheap verdict is dropped when a decision escalates).
- `examples/quickstart.py`: offline, keyless demo (one rung-2 decision, one close call escalated
  to a stub rung 7, both read back from the log), covered by `tests/test_quickstart.py`.
- README: a three-command first run, with uv (`uv sync`, `uv run examples/quickstart.py`), not pip.

- Design spec, prior art: an outside-games scan of LLM routers and cascades (RouteLLM,
  FrugalGPT, LiteLLM, Martian, Not Diamond, OpenRouter Auto, NadirClaw, LLMRouter, NVIDIA,
  vLLM Semantic Router) and a verdict: stay game-focused, routers inside packs only, generalize
  on a stated trigger. Full write-up: `docs/research/2026-11-04-llm-routers-and-cascades.md`.

### Changed
- README rewritten in plain language: why Jigsaw exists, the ladder, gate and log explained with
  the real defaults, the quickstart's actual output, a usage example that runs, and status/gaps.
- `examples/quickstart.py` now explains each decision as it happens: what the cheap scorer picked,
  why the gate did or didn't escalate (the score gap against the margin), and the log read back.
  With no path argument it writes a fresh temporary log each run.

## [0.1.0] - 2026-11-04

First public release (alpha). The API may change before 1.0.

### Added (2026-10-26, later)
- `Verdict.decision_id`: `Ladder.decide` sets it to the logged row's id, so the caller can record
  the outcome (`DecisionLog.set_outcome`) once the decision is carried out. None without a log.

### Added (2026-10-26: the first day)
- Repo skeleton and the design, `docs/specs/2026-10-26-jigsaw-design.md` (draft 2 after a referee
  review) (#1, #3).
- **Decision log** (`jigsaw.decision_log`): one SQLite row per decision with options, rung, the
  gate's reason, choice, primitives, legality and a later outcome; `rung_counts()` (#2). Safe to
  share between threads (#4).
- **Ladder and gate** (`jigsaw.ladder`): Request/Verdict, the Decider protocol, `normalise()`,
  GateConfig/Gate (human, high stakes, novelty, close call, cadence) and Ladder (#5). Two-option
  close calls can escalate: scores already in 0..1 are kept (#6).
