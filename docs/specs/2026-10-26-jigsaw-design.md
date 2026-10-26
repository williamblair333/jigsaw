# Jigsaw: design (draft 1, 2026-10-26)

Status: draft for Bill's review. Nothing here is built yet.

## The job

Game AI that decides with algorithms and programs first, and asks an LLM only when they can't.
Every decision is logged, so the system can be analysed and so repeated LLM calls can be
turned into rules over time. One engine; each game plugs in as a pack.

Bill's terms (2026-10-26): offload as much as possible to algorithms; use every tool for the job
it's best at; templates per genre; MTW2 is the only game pack for now; private now, public later.

## Prior art (searched 2026-10-26)

- **Vox Deorum** (Civilization V, arXiv 2512.18564, FDG '26): the LLM sets macro strategy and the
  game's own AI does the rest; over 2,327 games the LLM strategists matched the game's AI. The
  layered idea works. It has no ladder below the LLM, no gate, no cascade, no learning loop.
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

### 3. Decision ladder (engine), cheapest rung first
Each rung handles a decision or passes it up.

| Rung | Tool | Example (MTW2) |
|---|---|---|
| 0 | the game's own AI | anything no rung claims (Parley's control areas already do this) |
| 1 | rules / behavior trees | close popups, keep the capital garrisoned, auto-resolve |
| 2 | utility scoring | build, recruit, tax |
| 3 | planners (HTN, A*) | expand the intent "take Milan" into marches, a merge, a siege |
| 4 | search (MCTS) | only where a simulator exists (not MTW2) |
| 5 | small local model | classify: is this message a threat, is this offer fair |
| 6 | cheap cloud model | summaries, routine replies |
| 7 | strong model | strategy, diplomacy, persona, anything new |

### 4. Gate (engine): when to climb
A decision escalates when any of these hold:
- **close call**: the top two options score within a margin;
- **high stakes**: the game pack marks the decision kind (war, ceding land, the heir's marriage);
- **novelty**: no rule or recipe matches the situation;
- **a person is involved**: a human wrote, offered or asked;
- **cadence**: a strategy review every N turns.

Later the gate learns: per situation kind, how often the stronger rung *disagreed* with the
cheaper one. Where it agrees 95% of the time, stop asking; where it overrules, always ask.

### 5. Intent contract (engine)
LLM rungs answer with **intents** (`take Milan with Doge Enrico`, `peace with France, offer
2000`), never coordinates or unit ids. Rung 3 expands intents into primitives; the adapter's
legality check is the last gate. A weak model only has to choose a goal.

### 6. Decision log (engine): built first
One record per decision: game, turn, faction, decision kind, situation summary, options with
scores, the rung that decided, why it escalated (or didn't), the choice, the primitives sent, the
legality results, and the outcome when it arrives (filled in later turns). Stored locally
(SQLite or DuckDB-readable files). This is also Bill's "track every decision" system.

### 7. Distillation (engine)
From the log: situations where the LLM made the same call repeatedly become rule candidates,
reviewed before they join rung 1 or 2. Learning scores **outcomes**, not imitation, so the LLM's
bad habits aren't locked in. Routine choices learn fast; strategy learns slowly (outcomes arrive
many turns later).

### 8. Genre templates
Shared defaults per genre that a game pack fills in: decision kinds, derived maps, utility
considerations, HTN method skeletons, stakes table. First template: **grand strategy / 4X**.
Later: tactics/RTS, card and board games, RPG party.

### 9. Personas
Rulers stay present even on quiet turns: a one-line in-character note from the local model;
the strong model only when the gate escalates.

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

1. **Decision log**, wired into Parley so every decision from day one is recorded.
2. **Grand-strategy template + MTW2 pack skeleton**, with Parley as the adapter.
3. **First rung-2 and rung-3 deciders, paired with adapter coverage**: each decision-inventory
   row (`mtw2/docs/decision-inventory.md`, 92 rows, 28 doable today) becomes an action plus its
   default decider. Start with the click debt (event ids, popups), then the siege clock and the
   `take` intent.
4. **The gate**, rule-based first, learned once the log has data.
5. **Distillation**.

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
