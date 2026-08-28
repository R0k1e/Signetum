# Development Foundation

This repository publishes generic, versioned repository-development contracts:
a Python package and check-only CLI, independently identified schemas, and
explicitly composed policy profiles. Consuming repositories pin an immutable
release and keep ownership of architecture, requirements, plans, validation,
delivery, and acceptance.

```bash
uv sync --locked
uv run foundation validate --manifest path/to/repository.yaml
uv run pytest
uv build
```

The CLI writes one JSON result and exits nonzero for unsupported manifest or
profile identities. See `docs/ARCHITECTURE.md` for responsibility boundaries.
