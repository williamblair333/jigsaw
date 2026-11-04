# Handoff

## 2026-11-04: product brief and expert bar

**State:** `PRODUCT.md`, `STANDARDS.md`, the explaining quickstart and the plain-language README
are merged (#11–#13); the Gitea → GitHub push mirror is live (set up by the mtw2 session), so
don't push to GitHub by hand. An alternatives scan of LLM routers is in the spec's prior-art
section (PR open, `docs/prior-art-routers`); verdict: stay game-focused, routers only inside
packs. 36 tests pass. The first-run gate passes
(`python3 /opt/proj/Uncle-J-s-Refinery/features/product-quality/first_run_gate.py .`);
`standards_check.py --check .` is clean. The gate writes `.first-run-gate/` locally (ignored).
A Gemini referee caught one wrong status (`public-api-declared`: `__all__` already exists), now fixed.

**Next:** work the top open gaps in STANDARDS.md, in order: `log-both-verdicts` (a new
column, so do `schema-versioned` with it), `decider-failure-contained`, `full-request-replayable`.
The learned gate in the spec depends on the first one.

## 2026-11-04: v0.1.0, public

**State:** public on Gitea (`bill/jigsaw`) and GitHub (`williamblair333/jigsaw`, push mirror from
Gitea). Tag `v0.1.0`. Parley now pins `git+https://github.com/williamblair333/jigsaw@v0.1.0`
instead of the path, so a clean machine can install it. To ship a change to Parley: merge here,
tag a new version, then bump the pin in Parley's pyproject.toml and run `uv lock`.
No STANDARDS.md or PRODUCT.md yet: run the Uncle J skills pass here next.

## 2026-10-26: decision log, ladder and gate built; MTW2 uses them

**State:** main after the decision-id PR. `just test` (35 pass). `Verdict.decision_id` lets
Parley record outcomes for steward decisions. Private on Gitea (`bill/jigsaw`).

**Used by:** Parley (`/opt/proj/games/mtw2`) through a non-editable path dependency. After a
change here, run `uv sync --reinstall-package jigsaw` in Parley. Before either repo goes public,
make this a git or PyPI dependency.

**Live in Parley:** every ruler decision goes into the log (`<turn_root>/<game>.decisions.db`); seats
with `ladder = true` get adoptions answered by a rung-2 rule unless the gate escalates.

**Next, in order** (spec build order):
1. Gate in front of a whole ruler turn (quiet turns get a cheap note instead of a strong-model call).
2. Rung-2/3 deciders paired with MTW2 adapter rows (marriages and decision outcomes are in progress
   in Parley).
3. Measure the gate from the log: concordance rate and unforced regret (spec §4).
4. Templates and distillation only after MTW2 plays a full campaign.

**Working here:** Gemini writes and tests code in a worktree (`uv run pytest -q`, sandboxed for it).
Review its work; three real bugs were caught in review on day one.
