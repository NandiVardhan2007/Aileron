# Contributing to Aileron

1. Read `agent.md` and `rules.md`. Safety rules (`SAFE-*`) are non-negotiable.
2. Develop with `--backend null` and replay files first.
3. One logical change per PR. Use Conventional Commits.
4. New gesture? Add: spec in `docs/GESTURES.md`, config in `config/defaults.toml`, unit tests, replay fixtures.
5. Touching the hot path? Include before/after latency numbers (`tools/plot_latency.py`).
6. Changes to `safety/` or any `SAFE-*` behavior need two reviewers.

Checks before opening a PR:
```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest
```

Be kind in reviews. Accessibility and safety issues are always in scope, even for "just a demo".
