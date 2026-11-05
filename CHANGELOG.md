# Changelog

All notable changes to this project are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- The log keeps both answers when a decision escalates. `Decision` and the `decisions` table
  gain `cheap_choice` and `cheap_rung`: what the cheap rung picked before the gate sent the
  decision up. They stay empty when nothing escalated or no cheap rung answered. Comparing them
  with `choice` and `rung` gives the cheap-vs-model agreement rate (STANDARDS `log-both-verdicts`).
- The log file has a schema version (`SCHEMA_VERSION = 2`, kept in SQLite's `PRAGMA user_version`).
  Opening a v0.1.0 log adds the two new columns and keeps every row. A file from a newer Jigsaw is
  refused with a clear error. A file that is already current opens without a write lock, so a
  read-only copy can be queried (STANDARDS `schema-versioned`).

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
