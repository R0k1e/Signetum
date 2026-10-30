# Acceptance fixture architecture

This internal Python fixture exercises a rendered Signetum runtime independently
of the installed engine. `src/application` owns the toy application;
`tests/unit` and `tests/integration` exercise its declared native runner.
`signetum.toml` binds validation and `.agents/signetum/repo.yaml` binds policy.
Generated runtime modules are derived from the engine during render or test setup.
They are not a maintained copy of the product source.
