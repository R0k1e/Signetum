# Python and uv policy

Use `uv sync --locked`, `uv run`, and `uv build` as the only Python environment,
execution, and build authority. Test public behavior before implementation and
inspect built wheel contents.
