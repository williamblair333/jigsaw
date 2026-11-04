# jigsaw: agent notes

- The design lives in `docs/specs/`. Read the newest spec before changing behavior.
- Use the `justfile` recipes. One-line recipes over scripts; no logic in the justfile.
- Public (Gitea `bill/jigsaw`, mirrored to GitHub `williamblair333/jigsaw`): no secrets in the repo, ever. The env file stays untracked.
- `_review/` and `_reviewed/` are local and gitignored. Gemini research reports land in `_review/`.
- Gemini (via `ask_agy`) takes research, drafts and test-backed code in a worktree; it runs tests
  with `sandbox-run uv run pytest -q`. Verify its output before merging.
- The first game pack is MTW2 (`/opt/proj/games/mtw2`, the Parley project). Engine code stays
  game-agnostic: anything that names a game belongs in its pack.
- Releases: bump `version` in pyproject.toml, add a CHANGELOG section, tag `vX.Y.Z` on main.
  Parley pins a tag, so it sees a Jigsaw change only after a new tag and a bump of its pin.
- Never commit directly to `main`. Branch, PR on Gitea, merge.
