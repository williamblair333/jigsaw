# Changelog

All notable changes to this project are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `PRODUCT.md`: core job, users, success measures, first-run path, non-goals, UI principles and
  a `verify:` block. The first-run gate passes in a clean `python:3.12-slim` container.
- `STANDARDS.md`: the expert bar, 19 items ranked by impact, plus 3 ideas to test. Top gap:
  `log-both-verdicts` (the cheap verdict is dropped when a decision escalates).
- `examples/quickstart.py`: offline, keyless demo (one rung-2 decision, one close call escalated
  to a stub rung 7, both read back from the log), covered by `tests/test_quickstart.py`.
- README: a three-command first run.

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
