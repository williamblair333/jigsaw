# jigsaw: agent notes

- The design lives in `docs/specs/`. Read the newest spec before changing behavior.
- Use the `justfile` recipes. One-line recipes over scripts; no logic in the justfile.
- Public (Gitea `bill/jigsaw`, mirrored to GitHub `williamblair333/jigsaw`): no secrets in the repo, ever. The env file stays untracked.
- `_review/` and `_reviewed/` are local and gitignored. Gemini research reports land in `_review/`.
- Gemini (via `ask_agy`) takes research, drafts and test-backed code in a worktree; it runs tests
  with `sandbox-run uv run pytest -q`. Verify its output before merging.
- The first game pack is MTW2 (`/opt/proj/games/mtw2`, the Parley project). Engine code stays
  game-agnostic: anything that names a game belongs in its pack.
- Engine code stays game-agnostic: `tests/test_engine_game_agnostic.py` fails on a game or pack name in `src/jigsaw`.
- Releases: run `just contract` first (Parley's tests against this checkout; it must pass). Then bump
  `version` in pyproject.toml, add a CHANGELOG section, merge, and tag `vX.Y.Z` on main.
  Parley pins a tag, so it sees a Jigsaw change only after a new tag and a bump of its pin.
- Never commit directly to `main`. Branch, PR on Gitea, merge. Branch protection enforces it: direct
  pushes are refused, and a PR merges only when CI (`ci / test (3.11|3.12|3.13)`) is green.
- Gitea's merge API has answered HTTP 405 on a merge that went through. Check the PR's `merged`
  field, not the status code.
