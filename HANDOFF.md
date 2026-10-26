# Handoff

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
