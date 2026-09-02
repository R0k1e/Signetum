set positional-arguments

_signetum *args:
    mise exec -- uv run --no-project python .agents/repo-dev/runtime/lifecycle.py {{args}}

# Authoring utility; not a lifecycle operation.
change-open name:
    mise exec -- uv run --no-project python .agents/repo-dev/runtime/change_open.py {{name}}

workspace-open branch base:
    just _signetum workspace-open {{branch}} {{base}}

changed *args:
    just _signetum changed {{args}}

ready:
    just _signetum ready

batch-open *args:
    just _signetum batch-open {{args}}

batch-admit batch *args:
    just _signetum batch-admit --batch {{batch}} {{args}}

batch-continue batch:
    just _signetum batch-continue --batch {{batch}}

final:
    just _signetum final

batch-deliver source target expected-base expected-batch-tip:
    just _signetum batch-deliver {{source}} {{target}} {{expected-base}} {{expected-batch-tip}}
