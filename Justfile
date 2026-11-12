set positional-arguments

# Recipes forward "$@" so each argument reaches the engine as one argument.
_lifecycle *args:
    mise exec -- uv run signetum "$@"

workspace-open branch base:
    just _lifecycle workspace-open "$@"

ready *args:
    just _lifecycle ready "$@"

batch-open *args:
    just _lifecycle batch-open "$@"

batch-admit batch *args:
    just _lifecycle batch-admit --batch "$@"

batch-continue batch *args:
    just _lifecycle batch-continue --batch "$@"

final *args:
    just _lifecycle final "$@"

batch-deliver source target expected-base expected-batch-tip *args:
    just _lifecycle batch-deliver "$@"

# Local support utility; not a lifecycle operation.
maintenance *args:
    mise exec -- uv run signetum maintenance "$@"

# Local authoring and journal utility; not a lifecycle operation.
change *args:
    mise exec -- uv run signetum change "$@"

# Explicit development feedback; no workspace registration or readiness receipt.
test *args:
    mise exec -- uv run signetum test run --shard engine:pytest -- --no-cov "$@"
