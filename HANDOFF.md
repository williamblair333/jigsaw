# Handoff

## 2026-11-05: every STANDARDS item done; v0.9.0 tagged; Parley on v0.8.0

**State:**
- `main` is at v0.9.0, tagged on Gitea and the GitHub mirror.
- Parley's pin is v0.8.0 (bill/mtw2#395, merged). v0.9.0 is not pinned there: the mtw2 session moves the pin when it wants the new pieces.
- 210 tests pass. Pyright strict reports 0 errors.
- All 19 STANDARDS items are done. The 3 ideas (`shadow-audit-sample`, `skip-lot-gate`, `holdings-for-distillation`) are built in v0.9.0 and wait for a campaign log to test them.

**Built today:**
- v0.2.0: both verdicts in the log, the schema version, failing deciders pass up.
- v0.3.0: the stored request, `jigsaw replay`, `jigsaw concordance`.
- v0.4.0: the legality check, a failed log write keeps the verdict, WAL, `py.typed`, CI, the game-name test, `just contract`, the public API policy.
- v0.5.0: the intent contract (`jigsaw.intent`, `Ladder(expanders=...)`, replan once, model rungs must answer with an intent once expanders are set), and the `first-run` CI job in a clean container.
- v0.6.0: `Request.trace`. A rung asked after a failure sees what failed below it, and a caller can pass in failures from the game.
- v0.7.0: rung-2 utility scoring (`jigsaw.utility`: `UtilityDecider`, considerations, response curves, Mark's compensation) with the gate judging close calls on the decider's own scores, and resource reservation (`jigsaw.world.Budget`, `Verdict.costs`, `Ladder(budget=)`).
- v0.8.0: persona-weight intents. `Blackboard` holds weights per actor. `PersonaExpander(blackboard, allowed=)` checks them, and a new optional expander step, `commit(req, intent)`, writes them only for the answer that stands. `Consideration(persona=)` with `UtilityDecider(blackboard=)` reads them; a zero value stays a veto. Every intent type in spec §5 is built.
- v0.9.0: the three STANDARDS ideas as working pieces. `SkipLotGate` (`jigsaw replay --skip-lot` runs its test). `Ladder(shadow_rate=)` (shadow audits; `jigsaw concordance` shows shadow agreement). `Verdict.holding` with `jigsaw.distill` and `jigsaw holdings` (each holding scored on other logged decisions of its game and kind). The log moves to schema 5; v0.5.0 through v0.8.0 refuse it.
- Parley's logs: all 18 are schema 0, so `jigsaw concordance` compares 0 rows. Of the model ruler turns in the three biggest logs, 175 of 662 (26%) returned no orders. The findings went to the mtw2 session, which filed them in its `_review/`. It will message this repo before it starts the set_tax rung-2 rule and the quiet-turn gate.

**How the repo runs:**
- Branch protection on `main`: no direct pushes. A PR merges only with `ci / test (3.11|3.12|3.13)` and `ci / first-run` green.
- CLAUDE.md has the release steps, with `just contract` first.
- Check a PR's `merged` field, not the merge API's HTTP status.
- The log is at schema 5 from v0.9.0 (4 in v0.5.0–v0.8.0). Each release from v0.2.0 on refuses a newer schema than its own, and v0.1.0 has no check. Never move Parley's pin back past v0.5.0.

**Offloading:**
- Edit tasks for agy work in a worktree with a fixed brief and no commands. The docs in #27 and #31, and this entry, came out that way.
- agy reviews time out, so use a code-reviewer subagent.
- agy's sandbox can't run the uv tool runner, so run type checks yourself.
- Ollama and Heretic were down all day.

**Next:**
- Wait for mtw2's message, then help it adopt the pieces: a `UtilityDecider` for set_tax, `Budget` for the turn's gold, `legality=` from `validate.py`, and expanders for its first intents. Engine changes stay here, and pack code stays in Parley.
- Spec §2's derived maps and compact summaries, and §7 distillation, wait for Parley data: distillation needs a full campaign logged with v0.5.0 or later.
- Once Parley moves to v0.9.0 and logs a campaign: `jigsaw replay LOG --gate cadence=0 --skip-lot streak=20,sample=0.1` (skip-lot), `jigsaw concordance LOG` with shadow_rate set in Parley (shadow audit), and `jigsaw holdings LOG` (holdings). Each idea's test and kill criteria are in STANDARDS.md.
- No Parley pin bumps unless mtw2 asks. Tell it v0.9.0 exists and what moving to it changes (schema 5).

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
