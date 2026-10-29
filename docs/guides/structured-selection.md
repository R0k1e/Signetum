# Bind a repository-owned selection provider

An existing repository can retain its fine test selection without embedding its
old gate, retry loop or receipt writer. The optional `signetum.selection@1`
boundary supplies a plan to Signetum's existing execution and evidence owners.
Without a provider declaration, `ready` runs the full declared member-safe gate
and required checks; `changed` only explains that plan. Impact rules cannot narrow this default,
and tests are not skipped using ancestor evidence. Final always runs its complete
declared gate, including final-only checks.

```toml
[impact.provider]
protocol = "signetum.selection@1"
entrypoint = "tools/select_tests.py"
command = ["uv", "run", "--no-sync", "python", "{selector}"]
inputs = ["test-gates.toml", "tools/test_dependence.py"]
tools = [{name = "selection-python", identity_command = ["uv", "run", "--no-sync", "python", "--version"]}]
timeout_seconds = 60

[[impact.provider.targets]]
shard = "repo:tests"
roots = ["tests"]
argument_index = 3
```

The last binding assumes the declared shard command is, for example,
`["python", "-m", "pytest", "tests"]`. `argument_index` marks the beginning of
the replaceable command tail; every prefix argument is retained exactly. Use
the actual index of your existing supervised runner, including its flags.
Neither this declaration nor a profile selection invents a test framework.

## Producer input and output

The provider reads one JSON request from stdin and writes one JSON response to
stdout; diagnostics go to stderr. The request contains `protocol`, exact
`source`, `tree`, `base`, contribution `files`, declared `graph`, `profiles`,
committed input identities, observed `tools` and `request_digest`. Echo that
digest. Do not use timestamps, network state or unbound mutable cache state to
make a tree selection. Declare the entrypoint's implementation dependencies and
rules in `inputs` and all relevant interpreters/tools in `tools`.

A response has this shape:

```json
{
  "protocol": "signetum.selection@1",
  "request_digest": "sha256:<digest from the request>",
  "coverage": [
    {"path": "src/example.py", "status": "covered", "shards": ["repo:tests"], "reason": "Its dependent test file is selected."}
  ],
  "targets": [
    {"shard": "repo:tests", "tests": [{"path": "tests/test_example.py", "argument": "tests/test_example.py"}]}
  ]
}
```

Account for every requested path exactly once. Coverage names existing,
final-covered shards. Existing impact-rule selections and mandatory checks
remain in force. A covered path without a shard needs an explicit existing
impact rule; the producer cannot silently classify an unknown path as harmless.
An unexplained path retains conservative full-member validation and final
responsibility. Do not fabricate a coverage claim to avoid that fallback.

This version optionally refines file or file-node targets. Each argument names
its exact source file, optionally followed by `::` node components. Targets
must be committed regular files under declared roots; flags, foreign paths,
symlinks and mismatched file/argument identities refuse. A modified test file
must run as a whole file or through the full declared shard. Runners with other
target conventions can select whole declared shards without target refinement.

## Execution and evidence

`changed`, `ready` and admission share this boundary. The provider runs with the
existing deadline and owned-process supervisor. Failure to obtain a selection
is infrastructure failure; invalid output refuses before checks. The producer
must leave the source, bindings and observed tool identities unchanged.

The configuration binds the provider declaration. Its entrypoint and additional
inputs enter the existing artifact identity, and its tools enter tool identity.
Selected argv determines the actual graph and command proof. The receipt retains
the request/response identities in selection reasons, and admission recomputes
and compares the exact selection. No second gate or receipt store is introduced.

Inheritance still requires the existing exact input and graph proof, plus the
provider's explanation of intervening changes. Unknown coverage or changed tests
rerun the required checks. Final always executes original complete commands;
member targets never narrow it. Conflict continuation uses preparation and batch
static checks without another provider or member-test pass.

For first adoption use the repository's existing authority. Compare old and new
selection on fixed source cases, including new files, dependency changes,
modified tests, dynamic imports and unknown paths. Resolve discrepancies before
switching the default entrypoint. Keep product builds, preparation and policy
checks in repository tasks. Have the agent read historical working sets and
prepare ordinary decision proposals with original sources and rationale for review.
