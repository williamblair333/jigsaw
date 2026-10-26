# Jigsaw

Game AI that decides with algorithms first and asks an LLM only when it has to.

Rules, utility scoring and planners make the routine decisions. A gate decides when a decision
is close, risky or new enough to escalate, and then a cascade of models (local, cheap cloud,
strong) takes it. Every decision is logged, so repeated LLM calls can become rules over time.
One engine; each game plugs in as a pack, on top of a genre template.

Status: design draft. See `docs/specs/2026-10-26-jigsaw-design.md`. The first game pack is
Medieval II: Total War, through the Parley project.

```bash
just setup   # install dependencies
just test    # run the tests
```

License: GPL-3.0-or-later.
