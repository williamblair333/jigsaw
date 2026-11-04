# Jigsaw

Game AI that decides with algorithms first and asks an LLM only when it has to.

Rules, utility scoring and planners make the routine decisions. A gate decides when a decision
is close, risky or new enough to escalate, and then a cascade of models (local, cheap cloud,
strong) takes it. Every decision is logged, so repeated LLM calls can become rules over time.
One engine; each game plugs in as a pack, on top of a genre template.

Status: alpha (0.1.0). The decision log, the gate and the ladder work and are used by Parley;
templates and distillation are still design. See `docs/specs/2026-10-26-jigsaw-design.md`. The first game pack is
Medieval II: Total War, through the Parley project.

Try it in under two minutes, offline, with no API key (needs [uv](https://docs.astral.sh/uv/)):

```bash
git clone https://github.com/williamblair333/jigsaw && cd jigsaw
uv sync
uv run examples/quickstart.py
```

One clear-win decision stays at rung 2, a close call escalates to rung 7 (a stub plays the
model), and both are read back from the SQLite log.

Add it to your project from git (it isn't on PyPI yet):

```bash
uv add "jigsaw @ git+https://github.com/williamblair333/jigsaw@v0.1.0"
```

Work on it:

```bash
just setup   # install dependencies
just test    # run the tests
```

License: GPL-3.0-or-later.
