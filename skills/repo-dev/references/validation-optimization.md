# Optional validation optimization

Use only when requested or justified by a measured bottleneck. Keep the existing
runner, allocator, retry and receipt owners. Preparing the environment/build is
an explicit outer step. No option enables delivery or replaces full final checks.

## Python fine selection

`select-python --config <repo-relative.json>` reads the standard selection request
from stdin and emits `signetum.selection@1`. Configure the existing provider with
its entrypoint `.agents/repo-dev/runtime/protocol.py` and command:

```json
["python3", "{selector}", "select-python", "--config", "python-selection.json"]
```

The consumer configuration is:

```json
{
  "schema_version": 1,
  "source_roots": ["src"],
  "unit_roots": ["tests/unit"],
  "unit_shard": "repo:unit",
  "families": [{"paths": ["src/api/*"], "shards": ["repo:api-integration"]}],
  "dynamic_loaders": []
}
```

A dynamic-loader entry is `{"module":"owner.module","imports":["loaded.module"]}`; use exact module
names in the configured import namespaces. Declare configuration and implementation
files as provider inputs and bind the interpreter identity. Configure the unit
shard's target roots and command-tail index through the existing provider binding.
Do not put integration import reach into this algorithm; declared families own
integration. Unknown inputs, uncertain dynamic reach or parsing fall back safely.
Modified test/support files cannot disappear. No provider still means full member
checks, and final always executes original complete commands.

## Pytest scheduling

Use `schedule --log <existing-pytest-log> --output <new-weights.json>` to derive
hints from ordinary duration output; `--by-file` produces file costs for CI
partitions. Inspect and commit the resulting validation input. No extra timing
report is maintained.

Set `SIGNETUM_SCHEDULE_FILE` to a repository-owned JSON mapping of scheduling unit
to positive measured cost. Units are node IDs or sorted underscore-joined
`xdist_group` names. Add that file to `repository.lockfiles`, the protocol's
additional validation-input list. The runner uses loadgroup and the same allocation.
Missing entries keep normal conservative ordering; weights never skip tests or
set pass criteria. Generate measurements from ordinary duration output rather
than hand-maintain another performance report. CPU, phase and collection sums
are observations, not wall-clock guarantees or whole-process-tree memory peaks.

## CI file partitions

`partition plan --config <path> --output <outside-repository-plan.json>` enumerates
committed regular files before importing them. Configuration is also declared in
`repository.lockfiles`:

```json
{
  "schema_version": 1,
  "shard": "repo:unit",
  "roots": ["tests/unit"],
  "patterns": ["*/test_*.py"],
  "argument_index": 3,
  "slices": 2,
  "framework": "pytest",
  "weights": {},
  "groups": []
}
```

Patterns match whole repository-relative paths. The index replaces the original
command tail; verify it against the actual runner argv. Include all intended test
files. `pytest` statically preserves literal shared groups; unresolved groups
refuse planning. Other frameworks use `files` with explicit shared file groups.
A group entry lists files which must stay in one partition. Partitions must contain
executable selected tests; marker-only empty lanes are not successful evidence.

The result exposes the matrix. Each existing CI job runs:

```text
partition run --plan <plan.json> --index <n> --output <unique-result.json>
```

Prepare required dependencies/builds first. Upload result files through existing
CI artifacts. After all jobs finish, run on the same source and tool identities:

```text
partition combine --plan <plan.json> --result <result-0.json> --result <result-1.json> --job-status success --job-status success
```

Each plan has a distinct run identity: do not reuse an old plan for a new CI run.
Populate `--job-status` in partition-index order from actual current CI job
conclusions, never infer success from artifact presence. The success values above
are illustrative. Missing, cancelled, duplicate, failed, recovered, overlapping and mismatched
results cannot produce success. Exact groups and configured universe are part of
the plan. Configuration and runtime implementation inputs must remain bound.
Aggregation proves only the declared CI shard; it creates no readiness/final
receipt and authorizes no delivery. Other static and final-only obligations remain
with their existing owners. This uses ordinary CI artifacts, not a persistent
cross-machine service. No RAM volume or background deletion is required.
