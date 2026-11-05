# Jigsaw

Jigsaw is a Python library for game AI. It makes routine decisions with cheap code, and it asks
a language model only when a decision is hard, risky or new. It records every decision, so you
can see which ones keep needing a model and replace those with rules over time.

## Why

A language model can play a strategy game well, but every call costs money and takes seconds.
Most decisions in a game don't need one. If a farm scores 0.9 and walls score 0.3, a plain
"pick the highest score" makes the right call instantly. A model earns its cost only when the
answer isn't obvious: two options score almost the same, a war is at stake, or a human player
just made an offer.

Jigsaw is the part that decides which kind of decision you're looking at.

## How it works

Jigsaw has three parts.

**The ladder** holds your deciders, cheapest first. A *decider* is any object that looks at a
decision and either answers it or passes. Each decider sits on a *rung* from 0 to 7:

| Rung | What decides | Example |
|---|---|---|
| 0 | the game's own AI | what you get when no rung answers |
| 1 | fixed rules | close a popup, keep the capital garrisoned |
| 2 | scoring | build, recruit, tax |
| 3 | planners | turn "take Milan" into marches and a siege |
| 4 | search | only where you can simulate the game |
| 5 | a small local model | is this message a threat? |
| 6 | a cheap cloud model | routine replies, summaries |
| 7 | a strong model | strategy, diplomacy, anything new |

You write the deciders. Jigsaw comes with none, because they depend on your game.

**The gate** decides when to climb from the cheap rungs (below 5) to the model rungs (5 and up).
It escalates a decision when any of these hold:

- *close call*: the top two options score less than 0.10 apart;
- *high stakes*: you marked the decision's stakes at 0.7 or more;
- *novelty*: no cheap decider answered;
- *a person*: a human player is involved;
- *cadence*: every 10th turn, as a strategy review.

The margin (0.10), the stakes threshold (0.7), the cadence (10) and the rung where models start
(5) are settings in `GateConfig`. A human player or an unanswered decision always escalates.

**The log** writes each decision to a SQLite file: the options, the choice, the rung that made
it, and why it climbed. When a decision climbs, the row also keeps what the cheap rung picked
(`cheap_choice`, `cheap_rung`). Later you can record how it turned out. This is the part meant
to pay off over time. The goal is to learn, per kind of decision, how often the model agrees
with the cheap scorer, and to stop asking where it nearly always does. `jigsaw concordance`
reports that number. On the quickstart's log (`uv run examples/quickstart.py demo.db`):

```
$ uv run jigsaw concordance demo.db
game  kind     decisions  escalated  compared  agreed  agreement
demo  build    1          0          0         0       -
demo  recruit  1          1          1         0       0%
```

*Compared* counts escalations where a cheap rung had answered and a model rung then decided.
The one recruit decision went to the model, which overruled the cheap scorer, so agreement
is 0%. Over a real campaign, a kind near 95% agreement is one the gate can stop escalating.

The log file carries a version number. When a newer Jigsaw opens a log made by an older one, it
adds the missing columns and keeps every row. v0.1.0 can still read and write a newer file,
since the new columns may be empty. From v0.2.0 on, Jigsaw refuses a file newer than itself.

You can read the log while a game is writing to it: the file uses SQLite's WAL mode, so a reader
never makes a decision wait. One thing to know when you copy a log: recent writes can sit in
`<log>-wal` beside it until the log is closed. Copy all three files (`.db`, `-wal`, `-shm`), or
copy after the game has closed the log.

**Replay** reruns a log offline, which lets you tune the gate on a campaign you've already
played. Each row keeps the whole request, so you can ask "what if the close-call margin were
0.02 instead of 0.1?". On the quickstart's log:

```bash
uv run examples/quickstart.py demo.db
uv run jigsaw replay demo.db --gate margin=0.02
```
```
2 rows replayed, 0 skipped (logged before the request was stored)
escalated: 1 logged, 0 now
choice would change: 1
```

That run calls no model: the cheap rung's answer is already in the log. The recruit decision
(0.62 vs 0.58) is no longer a close call, so it would stay with the cheap scorer's spearmen
instead of the model's archers. `--ladder package.module:factory` runs a whole candidate ladder instead. Its
deciders run for real, so a model rung makes real calls. Replay records no decisions, though
opening a log from an older Jigsaw upgrades its layout, as any Jigsaw does. Rows logged before
v0.3.0 have no stored request, so replay skips them and says so. In Python, use
`jigsaw.replay.replay_gate` and `replay_ladder`.

`SkipLotGate` is one of the STANDARDS ideas (`skip-lot-gate`), borrowed from acceptance sampling
in manufacturing: after `streak` agreements in a row for a kind of decision in one game, it
escalates that kind only on a random `sample` of the escalations it would have made, and one
disagreement sends the kind back to always. Human, high-stakes and novelty escalations are never
skipped, and they don't count toward a streak either: only close calls and cadence reviews do. Test it on
a logged campaign with `uv run jigsaw replay LOG --gate cadence=0 --skip-lot streak=20,sample=0.1`:
"escalated: X logged, Y now" shows the calls saved, and "choice would change" counts the
decisions where skipping would have lost the model's different answer. The replay feeds the gate
the logged outcome only when it escalated itself, as a live game would.

## Try it

You need [uv](https://docs.astral.sh/uv/). This runs offline and needs no API key:

```bash
git clone https://github.com/williamblair333/jigsaw && cd jigsaw
uv sync
uv run examples/quickstart.py
```

It plays two decisions for a made-up kingdom. A stub stands in for the model. Here is the
second one, the close call:

```text
Turn 2: the northern kingdom must choose what to recruit. Options: spearmen 0.62, archers 0.58.
  The cheap scorer (rung 2) picks spearmen.
  The gate escalates: close call (0.62 vs 0.58). The top two scores are 0.04 apart,
  under the gate's 0.10 margin, so the scorer's pick is close to a coin flip.
  The model (rung 7) picks archers.
  Final: archers, decided at rung 7. Logged as decision #2.
```

The first decision (farm 0.90 against walls 0.30) never reaches the model. At the end the
script reads both decisions back from the log.

## Use it in your game

Add it from git (it isn't on PyPI yet):

```bash
uv add "jigsaw @ git+https://github.com/williamblair333/jigsaw@v0.1.0"
```

Then give the ladder your deciders, and ask it for each decision:

```python
from jigsaw import DecisionLog, Gate, Ladder, Option, Request, Verdict

class BestScore:
    rung = 2
    def decide(self, req: Request) -> Verdict | None:
        if not req.options:
            return None
        best = max(req.options, key=lambda o: o.score or 0)
        return Verdict(choice=best.name, rung=self.rung, reason="highest score")

class AskModel:
    rung = 7
    def decide(self, req: Request) -> Verdict | None:
        choice = ...  # call your model here; Jigsaw never calls one itself
        return Verdict(choice=choice, rung=self.rung, reason="model")

log = DecisionLog("decisions.db")
ladder = Ladder([BestScore(), AskModel()], Gate(), log)

verdict = ladder.decide(Request(
    game="mygame", turn=12, actor="red", kind="recruit", situation="raiders at the border",
    options=[Option(name="spearmen", score=0.62), Option(name="archers", score=0.58)],
))
# ...carry out verdict.choice in the game, then, turns later:
log.set_outcome(verdict.decision_id, "raid repelled", turn=14)
```

### A rung-2 scorer

`UtilityDecider` in `jigsaw.utility` scores each option on considerations. A consideration takes an input in 0..1 shaped by a response curve (`linear`, `power`, `logistic`, `step`). The decider multiplies the considerations together with Mark's compensation factor.

```python
from jigsaw import Consideration, UtilityDecider, linear

LEVEL = {"low": 0.0, "normal": 0.5, "high": 1.0}

TAX = UtilityDecider(
    kinds={"set_tax"},
    considerations=[
        # more tax when the treasury needs it
        Consideration("need", lambda r, o: 1 - abs(r.context["treasury_need"] - LEVEL[o.name]), linear()),
        # less tax when the town is restless
        Consideration("calm", lambda r, o: r.context["unrest"] * LEVEL[o.name], linear(-1, 1)),
    ],
)
```

The verdict carries each option's score, so the gate escalates when the top two scores are close, and the log keeps those scores.

### A budget for the turn

Many decisions in one turn often draw on the same gold or recruitment slots. `Budget({"gold": 3000, "recruit_slots": 4})` holds the turn's totals; call `reset(...)` each turn. A decider puts what its answer uses up in `Verdict(costs={"gold": 400})`. `Ladder(budget=budget)` refuses an answer the budget can't cover, so it passes up like an illegal one, and charges only the answer that stands. `reserve` is all-or-nothing and safe across threads, so two seats sharing a budget can't both spend its last gold. Call `budget.release(costs)` when the game rejects an order that was charged.

### Persona weights

A model can steer the cheap rungs without making every move, by setting flavor weights in 0..1, such as `{"aggression": 0.8}`, with an intent `Intent(verb="persona", args={"weights": {...}})`. `PersonaExpander(blackboard)` handles that verb: it checks each weight is a number in 0..1 (and, with `allowed=`, that its name is one you expect). The weights reach the `Blackboard` for the request's actor only if the answer stands, after your legality and budget checks. `Consideration(..., persona="aggression")` and `UtilityDecider(..., blackboard=blackboard)` read them: weight w raises that consideration's value to the power 2w, so 0.5 changes nothing, 0 switches it off, and 1 makes it count more sharply; a missing weight counts as 0.5. A value of 0 stays 0 whatever the weight, so a consideration that vetoes an option keeps vetoing it.

A decider returns `None` to pass the decision to the next rung. If no rung answers, the verdict
has `choice=""` and `rung=0`, and its `reason` says the game's own AI keeps the decision. If the
gate escalates but no model rung answers, you get the cheap rung's verdict, and its `reason`
says no higher rung was available.

A decider that raises an error also counts as passing. So a model rung that loses its network
connection doesn't stop the turn; the cheap answer stands. To treat a slow decider the same way,
pass `decider_timeout=` (in seconds) to `Ladder`. Each failure is listed in
`verdict.decider_errors` and in the log row, and logged as a warning on the `jigsaw` logger.

Give the ladder your game's rules with `legality=`. This is a function `(request, verdict)` that
returns `None` when the move is allowed, or the reason it isn't. The ladder runs it on every
answer. A refused answer counts as passing, so a model that names a unit you don't have loses
to the cheap rung's legal answer. If the check itself crashes, the answer is refused too: an
unverified move is never returned.

A model rung can answer with `Verdict(intent=Intent(verb="take", args={"target": "Milan"}))`.
`Ladder(expanders={"take": ...})` gives the pack's expander for each verb, whose
`expand(request, intent, failure)` returns primitives or None. The legality check runs on the
expanded plan. If the plan fails, the expander gets one more try with the reason in `failure`,
and if that fails too the answer passes up. Once `expanders` is set, a model rung (rung 5 and
up) that returns primitives instead of an intent is refused, so a model never emits raw game ids.
The intent is logged in a new `intent` column (schema 4).

`Request.trace` lists what already failed on a decision, oldest first. A caller can pass its own
entries, for example a step the game rejected, and they come first. A rung asked after a failure
gets a copy of the request whose trace holds each decider error and refusal below it, so a model
can see why the cheap answer was refused. The log stores the request as the caller passed it.

A failed log write (a full disk, a locked file) doesn't lose the decision either. The verdict
comes back with `decision_id=None` and `log_error` set, and `ladder.log_failures` counts them.
Watch that counter if the log matters to you: a log that fails every write still lets the game
run, so nothing else would tell you the data stopped.

## Status

Alpha, version 0.1.0. The API may change before 1.0.

- **Works:** the ladder, the gate and the log. Parley, an AI player for *Medieval II: Total
  War*, uses them.
- **Designed, not built:** a gate that learns from the log, genre templates, and *distillation*
  (turning repeated model answers into rules). See `docs/specs/2026-10-26-jigsaw-design.md`.
- **Known gaps:** listed and ranked in `STANDARDS.md`. The first one: the release checklist
  doesn't yet run the first-run check in a clean container before every tag.
- **Out of scope:** real-time games, and calling model providers. Your deciders do that.

## Versions and the public API

The public API is the names in `jigsaw.__all__` (`ConcordanceRow`, `Decider`, `Decision`, `DecisionLog`, `Gate`, `GateConfig`, `Ladder`, `Legality`, `Option`, `ReplayReport`, `ReplayRow`, `Request`, `SCHEMA_VERSION`, `Verdict`, `concordance`, `normalise`, `replay_gate`, `replay_ladder`), plus the `jigsaw` command line. Anything else, including underscore names and module internals, can change in any release.

Until 1.0, a minor release (0.x.0) may change the public API. A patch release (0.x.y) never does.

A change that breaks the public API first ships one minor release in which the old form still works and raises a `DeprecationWarning` naming the replacement. The old form goes away in the next minor release.

Every release bumps `version` in pyproject.toml, adds a CHANGELOG section, and is tagged `vX.Y.Z` on main after `just contract` passes.

## Work on it

```bash
just setup      # install dependencies
just test       # run the tests
just contract   # run Parley's tests against this checkout (before a release)
```

CI runs the tests on Python 3.11, 3.12 and 3.13 for every PR, and `main` accepts only PRs with
all three green.

License: GPL-3.0-or-later.
