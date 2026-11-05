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

### Outside games: LLM routers and cascades (searched 2026-11-04)

Question: should Jigsaw stay game-only, generalize its core, or adopt a router for the model
rungs? The full scan, with sources and the reasoning, is in
`docs/research/2026-11-04-llm-routers-and-cascades.md`. READMEs were read directly, and each
quoted claim was checked against its file.

| Tool | Non-model rungs? | Escalates on | Logs reason + outcome? | Learns / distills? | Open, maintained, library? |
|---|---|---|---|---|---|
| RouteLLM [1] | no, two models | query difficulty | no | trained offline on preference data [2] | Apache-2.0 library; last push 2024-08 |
| FrugalGPT [3] | no | a scorer judges each answer | no | learns model combinations; caches, fine-tunes | research code; last push 2025-02 |
| LiteLLM Router [4] | no | load, latency, cost, errors; prompt-complexity tiers | cost and deployment, no reason, no outcome | no | library + proxy; active |
| Martian [5] | — | — | — | — | router no longer offered; site lists research products |
| Not Diamond [6] | no | prompt → predicted best model | not stated | custom routers from uploaded evals | hosted API; Python SDK archived |
| OpenRouter Auto [7] | no | task type × community spend, cost tier | chosen model and task type, no reason | follows market spend, not your feedback | hosted only |
| NadirClaw [8] | no | classifier, then a verifier (τ=0.80) | local SQLite/JSONL | retraining in paid tier only | PolyForm Noncommercial (not open source) |
| LLMRouter [9] | no | complexity, cost, performance | not stated | online learning is a TODO | MIT library; active |
| NVIDIA llm-router [10] | no | predicted quality, latency, cost | dev-only stdout logs | from historical data | Apache-2.0 service; active |
| vLLM Semantic Router [11] | no | quality/latency/cost policy | not stated | not stated | Apache-2.0 server; active |

Research closest to the loop: Inter-Cascade [12] distills the strong model's answers into
reusable strategies retrieved into the weak model's prompt (not rules); Fanconi et al. [13]
cascade base model → large model → human, with online learning from human feedback.

**What it shows.** Every tool routes between models only. All judge the query or the answer;
none looks at the margin between a decision's own options, a stakes flag or a human in the loop.
None records an escalation reason together with a later outcome, and none distills model answers
into rules. The field is also unstable: RouteLLM is unmaintained, Not Diamond's SDK is archived,
Martian dropped its router, and OpenRouter swapped Not Diamond for its own rankings.

**Verdict (2026-11-04): stay game-focused for now; use a router inside packs, not the engine;
generalize only on a trigger.**

- *Generalize (rename `turn` to a step, add a time cadence): not yet.* The niche is open, but
  what would make Jigsaw worth generalizing is the learning half, and STANDARDS.md's top gaps are
  that half: `log-both-verdicts`, `full-request-replayable`, `gate-concordance-report`. The engine
  has no game logic, only game words on `Request`, so a rename stays cheap later. Done now, it
  breaks Parley's pinned API for no current user, with no deprecation policy yet
  (`release-practice`).
- *Adopt a router: in packs only.* PRODUCT.md's non-goal stands: the engine calls no model
  provider. Routers handle a different layer (which model and provider, retries, fallbacks,
  cost), and that layer lives in a pack's rung 5–7 decider. LiteLLM is the one candidate that
  is maintained, a library, and covers fallbacks and retries, which `decider-failure-contained`
  needs from a pack.
- *Take two ideas:* an answer-confidence escalation reason (FrugalGPT's scorer, NadirClaw's
  verifier), and a strategy store (Inter-Cascade) as a step before full rule distillation.
- *Revisit when:* a non-game user wants the engine (then add `step` beside `turn` and a time
  cadence, and deprecate the old names for one minor release); the concordance report shows
  real savings; or a router ships non-model tiers or outcome-based learning.

Sources: [1] github.com/lm-sys/RouteLLM; [2] Ong et al., arXiv 2406.18665;
[3] Chen, Zaharia, Zou, arXiv 2305.05176, github.com/stanford-futuredata/FrugalGPT;
[4] docs.litellm.ai/docs/routing and github.com/BerriAI/litellm; [5] withmartian.com, fetched
2026-11-04; [6] github.com/Not-Diamond/notdiamond-python (archived) and
docs.notdiamond.ai/docs/router-training-quickstart;
[7] openrouter.ai/docs/guides/routing/routers/auto-router; [8] github.com/NadirRouter/NadirClaw;
[9] github.com/ulab-uiuc/LLMRouter; [10] github.com/NVIDIA-AI-Blueprints/llm-router;
[11] github.com/vllm-project/semantic-router; [12] Wu et al., arXiv 2509.22984;
[13] Fanconi et al., arXiv 2506.11887. Repo activity and archive status: GitHub API, 2026-11-04.

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
point (threat, front lines, supply, settlement value). Every rung reads it. Built so far (2026-11-05): `jigsaw.world.Blackboard` holds persona weights per actor; state, history and derived maps stay in the pack.

Two additions from review:
- **Resource reservation**: deciders reserve resources (gold, recruitment slots, movement) before
  committing actions. Later deciders see what remains, preventing overspending across the turn. Built (2026-11-05): `jigsaw.world.Budget`, `Verdict.costs`, `Ladder(budget=...)`.
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

**Built (2026-11-05):** Goal intents, persona-weight intents (`PersonaExpander`, `Blackboard`, `Consideration.persona`), the replan-once protocol and escalation with the trace are all built.

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
5. **Rungs 2–3 and intents**: utility scoring, planners, and intent decomposition. Built so far (2026-11-05): utility scoring (`jigsaw.utility`) and intent decomposition (`jigsaw.intent`); planners are still the pack's own.
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
