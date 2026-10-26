# Jigsaw: design (draft 2, 2026-10-26)

Status: draft 2 (2026-10-26), after a referee review; for Bill's review.

## The job

Game AI that decides with algorithms and programs first, and asks an LLM only when they can't.
Every decision is logged, so the system can be analysed and so repeated LLM calls can be
turned into rules over time. One engine; each game plugs in as a pack.

Bill's terms (2026-10-26): offload as much as possible to algorithms; use every tool for the job
it's best at; templates per genre; MTW2 is the only game pack for now; private now, public later.

## Prior art (searched 2026-10-26)

- **Vox Deorum** (Civilization V, arXiv 2512.18564, FDG '26): the LLM sets macro strategy and the
  game's own AI does the rest; over 2,327 games it won as often as the game AI at ~$0.86 a game, with
  no gate, cache, or cascade. The layered idea works.
- **CivBench** (2026) benchmarks LLM strategists on top of Vox Deorum.
- **LLM planning + RL execution** (arXiv 2606.20014) matched a hand-built behavior tree.
- **Behavior tree + LLM review** (Zenodo 23222129) maps the hybrid patterns.
- Not found: an open framework with a full decision ladder, a gate on when to call the LLM, a
  cheap-to-expensive model cascade, and distillation of LLM decisions into rules. Nothing for
  Total War at all. That gap is Jigsaw.

## Pieces

```
            game pack (per game)                      engine (shared)
 ┌────────────────────────────────┐   ┌───────────────────────────────────────┐
 │ adapter: observe -> State       │──▶│ world model (blackboard + derived maps) │
 │          actions + legality     │◀──│ decision ladder  ◀── gate              │
 │ domain: rules, utility curves,  │   │ intent contract  ──▶ planners          │
 │         HTN recipes, intents    │   │ decision log ──▶ distillation           │
 └────────────────────────────────┘   └───────────────────────────────────────┘
                       genre template (grand strategy, ...) sits between them
```

### 1. Adapter (game pack)
Turns the game into a typed **State** and a set of **primitive actions**, each with a legality
check that returns a reason when it refuses. For MTW2 this is Parley's Lua bridge,
`protocol.py` and `validate.py`. Route order for any new action (Bill, 2026-10-25): an API or
mod call, then direct memory reads/writes, then an upstream change; screen clicks last, and a
click route is debt to replace.

### 2. World model (engine)
A blackboard: current state, history, events, plus derived maps computed once per decision
point (threat, front lines, supply, settlement value). Every rung reads it.

Two additions from review:
- **Resource reservation**: deciders reserve resources (gold, recruitment slots, movement) before
  committing actions. Later deciders see what remains, preventing overspending across the turn.
- **Compact summaries over raw state**: high-level summaries replace raw dumps for LLM rungs.
  Raw state grows uncontrollably (Vox Deorum prompts hit 100k tokens late game, degrading reasoning).

### 3. Decision ladder (engine), cheapest rung first
Each rung handles a decision or passes it up.

| Rung | Tool | Example (MTW2) |
|---|---|---|
| 0 | the game's own AI | unhandled seats / fallback (see MTW2 caveat below) |
| 1 | rules / behavior trees | close popups, keep the capital garrisoned, auto-resolve |
| 2 | utility scoring | build, recruit, tax |
| 3 | planners (HTN, A*) | expand the intent "take Milan" into marches, a merge, a siege |
| 4 | search (MCTS) | only where a simulator exists; not for MTW2 (no simulator) |
| 5 | small local model | classify: is this message a threat, is this offer fair |
| 6 | cheap cloud model | summaries, routine replies |
| 7 | strong model | strategy, diplomacy, persona, anything new |

**MTW2 caveat for rung 0**: MTW2's faction AI is all-or-nothing (`freezeFactionAI`). Both modes
carry risks: unfrozen, the game AI overwrites the ladder's moves (e.g. walking armies away);
frozen, unhandled areas (tax, public order, settlement garrisoning) collapse. Parley handles this
by dividing actions into control areas, freezing per seat during its turn, and running a watchdog
timer that unfreezes any frozen seat if its turn hangs.

### 4. Gate (engine): when to climb
A decision escalates when any of these hold:
- **close call**: the top two algorithmic options score within a narrow margin, with utilities
  normalised to 0..1 first;
- **high stakes**: state-sensitive impact (e.g. declaring war, ceding a citadel, an heir's marriage,
  or treasury near bankruptcy);
- **novelty**: for v1, simply no rule or recipe matched the current situation;
- **a person is involved**: a human wrote, offered, or asked;
- **cadence**: a strategy review every N turns to counter strategic inertia.

Later the gate learns: per situation kind, how often the stronger rung *disagreed* with the
cheaper one. Where it agrees 95% of the time, stop asking; where it overrules, always ask.

**Measuring the gate**:
- **Concordance rate**: how often the LLM agrees with the top algorithmic choice. If concordance
  exceeds 85%, the gate escalates too often on routine decisions, wasting tokens. Target: under 85%.
- **Unforced regret**: severe losses (lost settlements, bankruptcies, wiped armies) occurring 1–5
  turns after a purely algorithmic decision where the gate didn't escalate. High regret signals
  under-escalation.

### 5. Intent contract (engine)
LLM rungs answer with **intents** (`take Milan with Doge Enrico`, `peace with France, offer 2000`),
never coordinates or unit ids. Rung 3 expands intents into primitives; the adapter's legality check
is the last gate. A weak model only has to choose a goal.

**Intent types**:
- **Goal intents**: tactical or strategic objectives expanded by planners (e.g. `take`, `defend`, `bribe`).
- **Persona-weights intents**: borrowed from Vox Deorum. The LLM sets flavor weights (e.g. aggression,
  piety, merchant focus) that steer classical deciders on rungs 1–2 without micro-managing actions.

**Failure and replanning protocol**:
Each intent has an `intent_id`. When an expanded primitive action fails or is refused by the adapter:
1. The failure reports back to the originating intent.
2. The planner attempts to retry or replan alternative primitives once.
3. If replanning fails again, it escalates up the ladder with the failure reason and execution trace.

### 6. Decision log (engine): built first
One record per decision: game, turn, faction, decision kind, situation summary, options with scores,
rejected alternatives with sub-scores, the rung that decided, why it escalated (or didn't), the
choice, the primitives sent, the legality results, `intent_id` and `parent_id` links, a reference
to the state snapshot, and the outcome when it arrives (filled in later turns). Stored locally
(SQLite or DuckDB-readable files). This is also Bill's "track every decision" system.

### 7. Distillation (engine, after MTW2 plays a full campaign)
From the log: situations where the LLM made the same call repeatedly become rule candidates,
reviewed before they join rung 1 or 2. Learning scores **outcomes**, not imitation, so the LLM's
bad habits aren't locked in. Routine choices learn fast; strategy learns slowly (outcomes arrive
many turns later).

Guards against bad rules:
- **Shadow mode**: candidate rules run silently in shadow mode alongside live decisions before promotion.
- **Provenance**: every distilled rule links back to the log entries that generated it.
- **Auto-deprecation**: rules whose outcome quality drops over time are flagged and retired.

### 8. Genre templates
A stated goal for the framework, but extracted from MTW2 once it works rather than designed
up front.

Shared defaults per genre that a game pack fills in: decision kinds, derived maps, utility
considerations, HTN method skeletons, stakes table. First template: **grand strategy / 4X**.
Later: tactics/RTS, card and board games, RPG party.

### 9. Personas
Rulers stay present even on quiet turns: a one-line in-character note from the local model;
the strong model only when the gate escalates. Persona weights also steer classical deciders
via intent contract (§5).

## Model cascade (the tool belt)

| Need | Tool |
|---|---|
| deterministic decisions | rungs 1–3 (Python) |
| classify, tag, short notes | `ask_local` / heretic (local) |
| summaries, drafts, research, test-backed code | Gemini via `ask_agy` (Flash; Argon when its quota allows) |
| strategy, diplomacy, review, final calls | Claude |
| decision analytics | DuckDB over the log |
| lessons across games | memweave |

## Build order

1. **Decision log**: done (`src/jigsaw/decision_log.py`).
2. **Wire the log into Parley**: record every decision from day one.
3. **Gate plus rung-1 rules**: placed in front of Parley's existing LLM to cut costs immediately.
4. **Decider-plus-adapter pairs from MTW2 decision inventory**: 92 rows in `mtw2/docs/decision-inventory.md`.
   Start with click debt (event popups), then the siege clock (in progress).
5. **Rungs 2–3 and intents**: utility scoring, planners, and intent decomposition.
6. **Templates and distillation**: extract genre patterns and distill rules after a full campaign runs.

## Custom algorithms (MTW2 first)

- **Siege clock**: holdout vs relief arrival → assault, starve, or lift.
- **Front pressure**: influence map weighted by settlement value and enemy strength → garrisons.
- **Treaty value**: prices an offer (gold, trade, alliance) against current threats.
- **Learned gate**: the value of asking the LLM, per situation kind.

## Open questions

- Storage for the log: SQLite file per game, or Parquet for DuckDB? (lean: SQLite, export later)
- How Parley and Jigsaw split: Parley as the MTW2 pack inside this repo, or a separate repo that
  depends on Jigsaw? (lean: separate; Parley imports Jigsaw)
- Real-time games: out of scope for v1.
