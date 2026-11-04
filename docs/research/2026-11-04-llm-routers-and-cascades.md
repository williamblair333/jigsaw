# Alternatives scan: Jigsaw's core mechanism vs LLM routers and cascades (2026-11-04)

> **Using this later.** The short version is in the design spec's prior-art section. Reread this
> when one of the verdict's triggers fires: a non-game user wants the engine, the gate's
> agreement report shows real savings, or a pack needs a model client. This field moves fast,
> so treat anything here older than about three months as stale. Re-check a tool's README and
> its last push before relying on a row. To redo the scan, run the `alternatives-scan` skill
> with this file's subject and category; it records the result for the download gate.

**Goal (Bill, 2026-11-04):** decide whether Jigsaw should stay game-only, generalize its core,
or adopt or wrap an existing tool for its model rungs.
**Subject:** a ladder of deciders ordered cheapest first, rules and scoring and planners below
the models. A gate escalates on a close call, high stakes, novelty, a human or a cadence. Every
decision is logged so the gate can learn agreement rates and model answers can be distilled into rules.
**Category phrasings:** "LLM router / model cascade"; "cost-aware model selection"; one level
up, "hybrid decision system that escalates from rules to models and learns from its log".
**Searches:** `alternatives_scan.py search` ("llm router", "llm cascade cost", "model routing
framework", "hybrid rules llm decision escalation", "llm distillation into rules"); 6 web
searches; READMEs read for 9 repos. Gemini extracted 28 quotes; Claude grepped every one
(26 exact, 2 differ only by markdown bold).

## Table

| Tool | 1. Non-model rungs? | 2. Escalates on | 3. Logs reason + outcome? | 4. Learns / distills? | 5. Open, maintained, library? |
|---|---|---|---|---|---|
| **Jigsaw** (subject) | yes: rungs 0–4 | close call, stakes, novelty, human, cadence | reason yes, outcome yes (`set_outcome`) | designed, not built | GPL-3.0, active, library |
| **RouteLLM** (lm-sys) | no: "routing between 2 models" [R1] | query difficulty, learned win-rate threshold [R1, P1] | not stated [R1] | router trained offline on preference data [P1]; no distillation | Apache-2.0, library + server; **last push 2024-08-10** (GitHub API) |
| **FrugalGPT** (Stanford) | no | per query: a scorer judges the answer before the next model [P2] | no | learns which model combination to use; "LLM approximation" (cache, fine-tune) [P2] | Apache-2.0 research code; last push 2025-02-10 |
| **LiteLLM Router** | no: deployments of models [L1] | load, latency, cost, errors; auto router classifies prompt complexity into tiers [L1, L2] | callbacks log success/failure, deployment, cost; no escalation reason, no outcome [L1] | no | library + proxy; 62.7k★, pushed 2026-11-04; GitHub licence NOASSERTION |
| **Martian** | — | — | — | — | **router no longer offered**: homepage lists research products only [M1]; competitor reports say it pivoted to interpretability plus a gateway with explicit model choice [M2, M3] |
| **Not Diamond** | no [N1] | prompt → predicted best model, cost/latency tradeoff [N1] | not stated | custom routers trained on uploaded evaluation data, ≤10k samples per job [N2] | hosted API; **Python SDK repo archived** (GitHub API, last push 2025-12-11); RoRF trainer is open [N3] |
| **OpenRouter Auto Router** | no | ~30 task types × community spend share over a trailing 7 days, cost tier [O1] | response `model` field; task type with a metadata header; no reason [O1] | follows aggregate market spend, not your feedback [O1] | hosted only |
| **NadirClaw** (newer) | no | classifier, then a verifier: below τ=0.80 it "steps up to the next-best model" [NC1] | local JSONL + SQLite logs, export [NC1] | "Adaptive retraining loop" only in paid Pro [NC1] | **PolyForm Noncommercial**, source-available, not open [NC1]; proxy; active |
| **LLMRouter** (ulab-uiuc, newer) | no | task complexity, cost, performance [U1] | not stated | continual learning is a TODO [U1] | MIT, library + server, 3.1k★, active |
| **NVIDIA llm-router blueprint** | no | predicted quality, latency, cost [V1] | stdout logs of prompts and decisions "for development purposes" [V1] | data-driven routing from historical data [V1] | Apache-2.0 FastAPI service, active |
| **vLLM Semantic Router** | no | policy over quality, latency, cost [S1] | not stated | not stated | Apache-2.0, server, 6.4k★, active |
| *Research:* Inter-Cascade | no | weak model's deferral | — | strong model writes reusable strategies, retrieved into the weak model's context [P3] | paper |
| *Research:* Fanconi et al. | no; a human is the top tier | confidence-based deferral and abstention [P4] | — | online learning from human feedback [P4] | paper |

All "stars/pushed" figures: GitHub API, measured here 2026-11-04. Every cost/quality figure in
the sources is their own benchmark; none was measured here.

## What the table says

1. **No tool has non-model rungs.** Every router chooses between models. Rules, scoring and
   planners below the models exist only in Jigsaw and in one-off code (a "rules → engine → LLM"
   PR in Shugar03/dexter #29 [D1]).
2. **No tool escalates on decision-level signals.** Routers judge the *query* (difficulty, task
   type) or the *answer* (FrugalGPT's scorer, NadirClaw's verifier). None looks at the margin
   between the decision's own options, a stakes flag, or a human in the loop.
3. **No tool logs the escalation reason and a later outcome.** NadirClaw and NVIDIA log the
   routing decision; LiteLLM logs cost; none records how the decision turned out.
4. **Learning exists, distillation into rules doesn't.** Not Diamond trains on your uploaded
   evaluations; NadirClaw retrains in its paid tier; Inter-Cascade distills into prompts. None
   turns model answers into rules.
5. **The field is unstable.** RouteLLM hasn't been pushed since 2024-08, Not Diamond's SDK is
   archived, Martian dropped its router, OpenRouter replaced Not Diamond with its own rankings.

## Verdict

**(a) Stay game-focused for now, use (c) only inside packs, and defer (b) with a stated trigger.**

- **(b) generalize — not yet.** The niche is real: nobody else offers non-model rungs, a
  decision-level gate, an outcome log or distillation. But the half that would make Jigsaw worth
  generalizing isn't built. STANDARDS.md's top open gaps are exactly that half:
  `log-both-verdicts`, `full-request-replayable`, `gate-concordance-report`, and the learned gate
  and distillation behind them. The engine holds no game logic, only game words (`game`, `turn`,
  `actor` on `Request`). So renaming later is cheap, but renaming now breaks Parley's pinned API
  for no current user, and `release-practice` has no deprecation policy yet.
- **(c) adopt — in packs, not the engine.** PRODUCT.md's non-goal stands: Jigsaw doesn't call
  model providers. Routers solve a different layer: which model and provider, retries,
  fallbacks, cost. That layer belongs inside a pack's rung 5–7 decider. **LiteLLM** is the
  one candidate that is maintained, usable as a library, and covers fallbacks and retries, which
  a pack needs for `decider-failure-contained`. RouteLLM is unmaintained, Not Diamond's SDK is
  archived, Martian has no router, OpenRouter Auto ranks by community spend (not by your game),
  and NadirClaw's licence bars commercial use.
- **Ideas worth taking:** an *answer-confidence* gate signal (FrugalGPT's scorer, NadirClaw's
  τ=0.80 verifier) as a sixth escalation reason; Inter-Cascade's strategy repository as a
  middle step before full rule distillation.

**Cheapest test:** in Parley, wrap one rung-6 decider's model call in `litellm.Router` with a
fallback model. Check that a forced provider error still returns a verdict.

**What would change the answer:** (1) a second, non-game user (agent tool calls, ops triage)
asks to use the engine → do (b): `step` alongside `turn`, a time-based cadence, deprecate the
old names for one minor release. (2) `log-both-verdicts` and the concordance report exist and
show savings → the case for (b) gets evidence. (3) A router ships non-model tiers or
outcome-based learning → re-scan.

## Sources

- [R1] RouteLLM README, https://github.com/lm-sys/RouteLLM
- [P1] Ong et al., "RouteLLM: Learning to Route LLMs with Preference Data", arXiv 2406.18665
- [P2] Chen, Zaharia, Zou, "FrugalGPT", arXiv 2305.05176; code https://github.com/stanford-futuredata/FrugalGPT
- [P3] Wu et al., "From Deferral to Learning: Online In-Context Knowledge Distillation for LLM Cascades", arXiv 2509.22984
- [P4] Fanconi et al., "Cascaded Language Models for Cost-effective Human-AI Decision-Making", arXiv 2506.11887
- [L1] LiteLLM routing docs, https://docs.litellm.ai/docs/routing
- [L2] LiteLLM README (auto router, `complexity_router`), https://github.com/BerriAI/litellm
- [M1] https://withmartian.com (fetched 2026-11-04)
- [M2] TrustedRouter, https://trustedrouter.com/compare/martian (a competitor)
- [M3] ClawRouters, https://www.clawrouters.com/blog/best-open-source-llm-router (a competitor)
- [N1] Not Diamond Python SDK README (archived), https://github.com/Not-Diamond/notdiamond-python
- [N2] Not Diamond, "Training a custom router", https://docs.notdiamond.ai/docs/router-training-quickstart
- [N3] RoRF, https://github.com/Not-Diamond/RoRF
- [O1] OpenRouter Auto Router docs, https://openrouter.ai/docs/guides/routing/routers/auto-router
- [NC1] NadirClaw README, https://github.com/NadirRouter/NadirClaw
- [U1] LLMRouter README, https://github.com/ulab-uiuc/LLMRouter
- [V1] NVIDIA llm-router blueprint README, https://github.com/NVIDIA-AI-Blueprints/llm-router
- [S1] vLLM Semantic Router README, https://github.com/vllm-project/semantic-router
- [D1] Shugar03/dexter PR #29, https://github.com/Shugar03/dexter/pull/29
