# Jigsaw: the expert bar

Written from the seats of a senior commercial game-AI programmer, an ML systems engineer who
runs model cascades, a data engineer who owns long-lived logs, and an open-source library
maintainer. The goal (PRODUCT.md): decide with cheap algorithms first, escalate to a model only
when it pays, and log every decision so escalations can be learned away.

Ranked by impact on that goal, highest first. A partial counts as open. The ideas came from
`think-wider` (2026-11-04). They're hypotheses until their test pays off.

Sources for the canon: Isla, "Handling Complexity in the Halo 2 AI" (GDC 2005); Mark,
*Behavioral Mathematics for Game AI* (2009); Rabin (ed.), *Game AI Pro* (2013); Nygard, *Release
It!* (2007); Kleppmann, *Designing Data-Intensive Applications* (2017); Chen et al., FrugalGPT
(arXiv 2305.05176); Ong et al., RouteLLM (arXiv 2406.18665); PEP 387 and PEP 561.

```yaml
phase: alpha library, one consumer (Parley) — making it reliable enough that campaigns run unattended and their logs can teach the gate
standards:
  - id: log-both-verdicts
    area: learning loop
    bar: When a decision escalates, its log row holds the cheap rung's choice and rung next to the final one, so agreement is computable from the log alone
    why: a routing engineer can't learn when to stop asking the strong model if the log drops the answer it was checking
    status: done
    evidence: tests/test_both_verdicts.py
  - id: decider-failure-contained
    area: game AI
    bar: A decider that raises or exceeds its time budget is treated as passing up, and the reason is logged; a test proves a raising rung-7 decider still yields a verdict
    why: the AI must never freeze or crash the campaign because one rung (usually the network one) failed
    status: done
    evidence: tests/test_decider_failure.py
  - id: full-request-replayable
    area: evaluation
    bar: Each log row stores the whole Request (stakes, human, context, options), and a replay command reruns any logged rows through a candidate gate or ladder offline
    why: thresholds and prompts get tuned against recorded situations, not live games
    status: done
    evidence: tests/test_replay.py
  - id: schema-versioned
    area: data
    bar: The log records its schema version in PRAGMA user_version and migrates older files forward on open; a test opens a v1 file with current code
    why: campaign logs outlive releases, and Parley moves its pin forward
    status: done
    evidence: tests/test_both_verdicts.py
  - id: gate-concordance-report
    area: learning loop
    bar: One command reports, per game and decision kind, how often the escalated rung agreed with the cheap one
    why: the spec's 95%-agreement rule needs a number per kind; RouteLLM's savings range from 35% to 85% by task type
    status: done
    evidence: tests/test_report.py
  - id: log-write-failure-contained
    area: data
    bar: A failed log write never discards the verdict; it is counted and surfaced to the caller, and a test simulates a failing write
    why: losing one log row is recoverable, losing the turn is not (Release It!, bulkheads)
    status: done
    evidence: tests/test_log_write_failure.py
  - id: every-decision-logged
    area: learning loop
    bar: Every Ladder.decide call with a log writes exactly one row and returns its id
    why: the learning loop is only as good as its coverage
    status: done
    evidence: tests/test_ladder.py
  - id: escalation-reason-named
    area: game AI
    bar: Every verdict and log row names why it climbed (close call, high stakes, novelty, human, cadence) or that no rung answered
    why: the gate can't be tuned on reasons nobody recorded
    status: done
    evidence: tests/test_ladder.py
  - id: scores-comparable
    area: game AI
    bar: The gate compares options on one 0..1 scale and keeps pack-calibrated 0..1 scores as given
    why: a close-call margin is meaningless across mixed scales (Mark, response curves)
    status: done
    evidence: src/jigsaw/ladder.py
  - id: legality-before-verdict
    area: game AI
    bar: The ladder runs a pack-supplied legality check on a verdict's primitives before returning it, and an illegal verdict passes up instead of being sent
    why: neither planners nor models can be trusted with live game constraints
    status: partial
    evidence: src/jigsaw/decision_log.py (a legality field is logged; the ladder never checks it)
  - id: ci-on-every-pr
    area: release
    bar: Gitea Actions runs `just test` on Python 3.11, 3.12 and 3.13 for every PR, and merging needs it green
    why: a library with a pinned consumer can't rely on someone remembering to run tests
    status: open
    evidence: no workflow file in the repo
  - id: first-run-proven
    area: release
    bar: The PRODUCT.md verify block passes in a clean container before every tag
    why: a stranger's first two minutes decide whether there is a second user
    status: partial
    evidence: PRODUCT.md (passed locally 2026-11-04; not wired into CI or the tag step)
  - id: consumer-contract-test
    area: release
    bar: Before a tag, Parley's test suite runs against the candidate Jigsaw commit
    why: the one consumer is the real API contract; finding a break after the pin bump is late
    status: open
    evidence: Parley only meets a change after the tag and its pin bump
  - id: engine-game-agnostic
    area: architecture
    bar: A test fails if src/jigsaw names a game or a game pack
    why: the engine's value is reuse across packs; one leaked name turns into ten
    status: partial
    evidence: CLAUDE.md (the rule is written down, not checked; decision_log.py's docstring already names Parley)
  - id: intent-contract
    area: game AI
    bar: Model rungs return a structured intent that deterministic rungs expand into primitives; a model never emits raw game ids
    why: models are good at goals and bad at transient ids (Game AI Pro, HTN)
    status: open
    evidence: spec piece 5; not built
  - id: concurrent-readers
    area: data
    bar: The log opens in WAL mode so an analysis read during a campaign never blocks a decision write
    why: the log is meant to be queried while games run
    status: open
    evidence: DecisionLog.__init__ sets no journal_mode
  - id: public-api-declared
    area: release
    bar: jigsaw/__init__.py exports the public API with __all__, and the README states that anything outside it can change without a major bump
    why: without a declared surface every helper becomes a promise
    status: partial
    evidence: src/jigsaw/__init__.py (__all__ declares 10 names; the policy isn't written down)
  - id: typed-package
    area: release
    bar: The package ships py.typed and passes pyright in strict mode
    why: pack authors implement the Decider protocol, and types are its documentation
    status: open
    evidence: no py.typed marker
  - id: release-practice
    area: release
    bar: Every tag has a CHANGELOG section and a version bump, and breaking changes get one minor release of DeprecationWarning first
    why: PEP 387; Parley pins tags
    status: partial
    evidence: CHANGELOG.md (tags and changelog exist; no deprecation policy)
ideas:
  - id: shadow-audit-sample
    idea: Send a random 2-5% of non-escalated decisions to the strong rung in shadow (logged, not acted on) to measure the gate's miss rate
    from: radiology quality assurance (discordance audits of unflagged reads)
    test: over one Parley campaign, the shadow sample finds kinds whose disagreement rate differs from the escalated-case rate by more than 10 points
    kill: shadow and escalated disagreement rates match within 5 points for every kind
    status: untested
  - id: skip-lot-gate
    idea: Per decision kind, escalate less often after an agreement streak and snap back to always after one disagreement
    from: manufacturing acceptance sampling (ANSI/ASQ Z1.4 switching rules)
    test: replayed over logged campaigns, it cuts strong-rung calls by 30%+ with no rise in disagreement on the decisions it skipped
    kill: savings under 10%, or misses concentrate in high-stakes kinds
    status: untested
  - id: holdings-for-distillation
    idea: Each rung-7 verdict records a structured holding (the condition and the choice) that distillation can turn into a rung-1 rule
    from: common law (appellate holdings binding lower courts)
    test: 20 logged holdings from one campaign yield at least 5 rules that agree with the model on 90%+ of replayed cases
    kill: fewer than 2 usable rules
    status: untested
```
