set positional-arguments

_lifecycle *args:
    mise exec -- uv run signetum lifecycle {{args}}

workspace-open branch base:
    just _lifecycle workspace-open {{branch}} {{base}}

changed *args:
    just _lifecycle changed {{args}}

ready:
    just _lifecycle ready

batch-open *args:
    just _lifecycle batch-open {{args}}

batch-admit batch *args:
    just _lifecycle batch-admit --batch {{batch}} {{args}}

batch-continue batch:
    just _lifecycle batch-continue --batch {{batch}}

final:
    just _lifecycle final

batch-deliver source target expected-base expected-batch-tip:
    just _lifecycle batch-deliver {{source}} {{target}} {{expected-base}} {{expected-batch-tip}}

# Local support utility; not a lifecycle operation.
maintenance *args:
    mise exec -- uv run signetum maintenance {{args}}

# Local authoring and journal utility; not a lifecycle operation.
protocol *args:
    mise exec -- uv run signetum protocol "$@"

change-open name:
    just protocol change-open "$@"

# Explicit development feedback; no workspace registration or readiness receipt.
test *args:
    just -- protocol test --shard engine:pytest -- --no-cov "$@"
