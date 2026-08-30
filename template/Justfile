set positional-arguments

_reposeal *args:
    uv run --no-project python .agents/repo-dev/runtime/lifecycle.py {{args}}

# Authoring utility; not a lifecycle operation.
change-open name:
    uv run --no-project python .agents/repo-dev/runtime/change_open.py {{name}}

workspace-open branch base:
    just _reposeal workspace-open {{branch}} {{base}}

changed base *args:
    just _reposeal changed {{base}} {{args}}

ready base:
    just _reposeal ready {{base}}

batch-open *args:
    just _reposeal batch-open {{args}}

batch-admit batch *args:
    just _reposeal batch-admit --batch {{batch}} {{args}}

batch-continue batch:
    just _reposeal batch-continue --batch {{batch}}

final:
    just _reposeal final

batch-deliver source target expected-base expected-batch-tip:
    just _reposeal batch-deliver {{source}} {{target}} {{expected-base}} {{expected-batch-tip}}
