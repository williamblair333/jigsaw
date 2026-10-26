# Changelog

All notable changes to this project are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added (2026-10-26: the first day)
- Repo skeleton and the design, `docs/specs/2026-10-26-jigsaw-design.md` (draft 2 after a referee
  review) (#1, #3).
- **Decision log** (`jigsaw.decision_log`): one SQLite row per decision with options, rung, the
  gate's reason, choice, primitives, legality and a later outcome; `rung_counts()` (#2). Safe to
  share between threads (#4).
- **Ladder and gate** (`jigsaw.ladder`): Request/Verdict, the Decider protocol, `normalise()`,
  GateConfig/Gate (human, high stakes, novelty, close call, cadence) and Ladder (#5). Two-option
  close calls can escalate: scores already in 0..1 are kept (#6).
