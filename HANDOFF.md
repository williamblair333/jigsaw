# Handoff

## 2026-11-05: every STANDARDS item done; v0.7.0; Parley on v0.7.0

**State:**
- `main` is at v0.7.0, tagged on Gitea and the GitHub mirror.
- Parley's pin moves to v0.7.0 (bill/mtw2#394, merged).
- 153 tests pass. Pyright strict reports 0 errors.
- All 19 STANDARDS items are done. The 3 ideas are untested: `shadow-audit-sample`, `skip-lot-gate`, and `holdings-for-distillation`.

**Built today:**
- v0.2.0: both verdicts in the log, the schema version, failing deciders pass up.
- v0.3.0: the stored request, `jigsaw replay`, `jigsaw concordance`.
- v0.4.0: the legality check, a failed log write keeps the verdict, WAL, `py.typed`, CI, the game-name test, `just contract`, the public API policy.
- v0.5.0: the intent contract (`jigsaw.intent`, `Ladder(expanders=...)`, replan once, model rungs must answer with an intent once expanders are set), and the `first-run` CI job in a clean container.
- v0.6.0: `Request.trace`. A rung asked after a failure sees what failed below it, and a caller can pass in failures from the game.
- v0.7.0: rung-2 utility scoring (`jigsaw.utility`: `UtilityDecider`, considerations, response curves, Mark's compensation) with the gate judging close calls on the decider's own scores, and resource reservation (`jigsaw.world.Budget`, `Verdict.costs`, `Ladder(budget=)`).
- Parley's logs: all 18 are schema 0, so `jigsaw concordance` compares 0 rows. Of the model ruler turns in the three biggest logs, 175 of 662 (26%) returned no orders. The findings went to the mtw2 session, which filed them in its `_review/`. It will message this repo before it starts the set_tax rung-2 rule and the quiet-turn gate.

**How the repo runs:**
- Branch protection on `main`: no direct pushes. A PR merges only with `ci / test (3.11|3.12|3.13)` and `ci / first-run` green.
- CLAUDE.md has the release steps, with `just contract` first.
- Check a PR's `merged` field, not the merge API's HTTP status.
- The log is at schema 4. v0.2.0 through v0.4.0 refuse it, and v0.1.0 has no check. Never move Parley's pin back past v0.5.0.

**Offloading:**
- Edit tasks for agy work in a worktree with a fixed brief and no commands. The docs in #27 and #31, and this entry, came out that way.
- agy reviews time out, so use a code-reviewer subagent.
- agy's sandbox can't run the uv tool runner, so run type checks yourself.
- Ollama and Heretic were down all day.

**Next:**
- Wait for mtw2's message, then help it adopt the pieces: a `UtilityDecider` for set_tax, `Budget` for the turn's gold, `legality=` from `validate.py`, and expanders for its first intents. Engine changes stay here, and pack code stays in Parley.
- Persona-weight intents (spec §5) need a blackboard that rungs 1–2 read; the rest of spec §2 (derived maps, compact summaries) isn't built.
- Test the 3 STANDARDS ideas on a v0.5.0-or-later Parley campaign log with `jigsaw concordance` and `jigsaw replay`.

## 2026-11-04: product brief and expert bar

**State:** `PRODUCT.md`, `STANDARDS.md`, the explaining quickstart and the plain-language README
are merged (#11–#13); the Gitea → GitHub push mirror is live (set up by the mtw2 session), so
don't push to GitHub by hand. An alternatives scan of LLM routers is summarized in the
spec's prior-art section and written up in full in
`docs/research/2026-11-04-llm-routers-and-cascades.md` (#14). Verdict: stay game-focused, use a
router (LiteLLM) only inside packs' model deciders, generalize only on the triggers listed there.
36 tests pass. The first-run gate passes
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
