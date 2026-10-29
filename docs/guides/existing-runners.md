# Adopt existing application runners

The protocol does not parse application code or select an application language.
Optional `python-existing@1`, `node-existing@1` and `rust-existing@1` adapters
propose bindings for commands the repository already owns. They do not install
dependencies, introduce a test framework or rewrite application metadata.
Other languages can bind commands directly through the same validation schema.

## Inspect, preview and apply

Ask the agent to prepare adoption using the repository's existing approval
process. Install a reviewed engine once as described in the [first-use guide](../../QUICKSTART.md).
The agent runs:

```bash
signetum adopt inspect --repository .
signetum adopt preview --repository . --request /tmp/adoption-request.json --output /tmp/adoption-plan.json
signetum adopt apply --repository . --plan /tmp/adoption-plan.json --expected-plan <approved-plan-digest>
```

`inspect` reads repository facts and executes no project command. The agent
prepares the disposable request; users review the preview, not protocol fields.
The request contains `manifest` (the complete reviewed `signetum.toml` text),
`policy` (the merged repository policy YAML text), and optional `interpreter`
(literal host Python argv, default `["python3"]`). Merge existing authorities
rather than replacing their settings. Name actual tools, lockfiles, preparation,
member, batch-static and final checks. Keep outside-world checks final-only.
The declared architecture file must already exist. Inspect the environment and
Mise/Worktrunk availability before promising workspace operation success.

The preview retains the source commit, before/after file contents and exact
runtime payload from the installed engine. It shows binding diffs and the file
inventory; review existing runtime replacements as an explicit local upgrade.
Only `apply` writes files. It requires that preview's exact digest, refuses
changed source, target files or symlink paths, and supports unchanged retries.
An ordinary application error rolls back files written by that invocation;
an interrupted process may leave partial files, so inspect before a fresh preview.

The payload supplies `.agents/repo-dev/run`, protocol runtime and workflow
instructions, then adds one pointer to `AGENTS.md`. Existing Justfile and
application metadata are untouched. Local commands are:

```bash
sh .agents/repo-dev/run protocol current
sh .agents/repo-dev/run workspace-open <branch> <exact-base>
sh .agents/repo-dev/run ready
```

The installed Skill discovers this launcher automatically. Template and already
adopted repositories can retain their existing `just protocol` binding. There
is one runtime and one execution owner; no project commands run during preview
or application, and neither creates approval or readiness. Commit the accepted
adoption through the repository's existing process before using the new workflow.

## Generate a binding proposal

Inspect the repository's actual test command, required tool identities and
validation inputs first. Keep the input request disposable. For example, an
existing Node repository whose test script is already `npm test` can request:

```json
{
  "language": "node",
  "command": ["npm", "test"],
  "tools": [
    {"name": "node", "identity_command": ["node", "--version"]},
    {"name": "npm", "identity_command": ["npm", "--version"]}
  ],
  "timeout_seconds": 120
}
```

```text
just protocol runner --request <disposable-request-path>
```

Before the local utility exists, generate the same proposal from a reviewed
engine checkout with `uv run signetum protocol runner --request <path>`. It needs
no access to the application project and writes no adoption files.

The result is an unapproved configuration fragment. It preserves the exact argv
and tool declarations; generating it executes nothing. Use the real existing
runner instead of copying this example when the repository uses another task.
Python can retain unittest, pytest or its existing command wrapper. Rust can
retain its existing Cargo or task-runner arguments. Declare every relevant
runtime and runner identity rather than guessing from a filename extension.

## Keep repository authorities

Merge the proposed application shard into the repository-owned validation
configuration as an ordinary approved adoption change. Preserve its core
contract checks, preparation commands, batch checks, final-only checks, impact
rules and existing lockfile/input bindings. The adapter does not replace that
configuration or automatically activate checks from a profile selection.
Use this adapter for source-bound tests; retain outside-world checks in their
existing final-only declarations.

The copied protocol runtime uses a host Python interpreter. A Node or Rust
application does not need a Python project, a Python application runner or the
Python default profile. Install the standard skill separately, bind its local
utility to the repository runtime, and keep application setup in the existing
repository authority. See [customizing](customizing-the-template.md) for the
binding and evidence boundaries.

## Verify the adopted path

Use a registered member and one approved change record. A failing application
test must fail ordinary readiness without a success receipt. Fix the source,
run ordinary readiness again, admit that exact tip and validate its frozen
batch. Do not clear a failure with a narrow retry or invent a second runner.
Inspect the generated review before any separately authorized delivery.

Native acceptance exercises this path for Python, Node and Rust through both
the engine and the generated runtime frontend. It preserves the application
metadata and locks, and Node/Rust cases create no Python project metadata.
These native host-tool cases are final-only world tests, not reusable member
credentials for the engine. Pure binding and portable CLI contracts stay in
the member suite. Local tests do not imply publication or cross-machine support.

## Repositories with existing fine selection and decision constraints

Use the [structured selection boundary](structured-selection.md) when retaining
repository-owned test dependence or contract-family selection. The optional
existing-runner adapter alone does not reproduce those algorithms. Keep one
execution, retry and receipt owner rather than nesting an old complete gate.
Without a provider, diagnostics and readiness run the full declared member gate.
Have the agent organize historical working sets into ordinary reviewed decision
proposals, retaining source references and rationale without format-specific
parsing or inferred approval.
