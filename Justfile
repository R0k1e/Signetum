set positional-arguments

_lifecycle *args:
    mise exec -- uv run reposeal lifecycle {{args}}

workspace-open branch base:
    just _lifecycle workspace-open {{branch}} {{base}}

changed base *args:
    just _lifecycle changed {{base}} {{args}}

ready base:
    just _lifecycle ready {{base}}

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
