# Repository binding contract

The agent uses this reference to prepare adoption. User setup begins with
[First use](../../QUICKSTART.md); the installed Skill owns the setup procedure.
The same contract serves new and existing projects after ordinary initialization.

## Adoption request

`signetum adopt preview --repository . --request <request.json> --output <plan.json>`
accepts:

- `manifest`: complete reviewed `signetum.toml` text.
- `policy`: merged repository policy YAML, retaining actual authorities and delivery.
- `interpreter`: optional literal host Python argv, default `["python3"]`.

The declared architecture must exist. Bind actual preparation, member, batch and
final commands, tool identities, locks and additional validation inputs. Keep
outside-world checks final-only. Preserve application metadata and Justfile.
The payload adds a local launcher, portable runtime, workflow reference and an
Agent-contract pointer; it does not supply a new application environment.

Preview records the exact base, before/after bytes and runtime identity.
`signetum adopt apply --repository . --plan <plan.json> --expected-plan <digest>`
requires that exact approved plan and unchanged targets. Ordinary write errors
roll back that invocation; abrupt interruption requires inspection and a fresh
preview. Neither operation executes application commands or creates approval.

## Existing runner proposal

Optional `python-existing@1`, `node-existing@1` and `rust-existing@1` adapters
propose bindings without installing tools or detecting languages from paths.
Other languages bind commands directly through the same validation schema.
`signetum protocol runner --request <request.json>` accepts, for example:

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

The result is an unapproved configuration fragment, not a complete adoption.
Merge its application shard deliberately with retained core/preparation/batch/final
checks and declared inputs. Selecting a profile never activates omitted commands.
The host interpreter does not impose Python application metadata on Node or Rust.

The installed path is verified through representative real consumers and native
runner acceptance. See [validation responsibilities](../architecture/validation-and-delivery.md)
for selection, resource, recovery and source-bound receipt semantics.
