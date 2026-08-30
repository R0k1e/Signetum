# Development Foundation

This repository is a complete GitHub Template for starting a repository with a
governed development lifecycle. Creating from the template is a one-time copy;
existing repositories do not track, pull, or automatically adopt later changes.
The included package, CLI, schemas, profiles, and repo-dev guidance are owned
and evolved inside each repository created from it.

```bash
uv sync --locked
uv run foundation validate --manifest path/to/repository.yaml
uv run pytest
uv build
```

The CLI writes one JSON result and exits nonzero for unsupported manifest or
profile identities. See `docs/ARCHITECTURE.md` for responsibility boundaries.

There is deliberately no template-update command, upstream merge contract,
subtree, or downstream adoption protocol.
