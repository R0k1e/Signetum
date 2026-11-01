# Repository binding contract

The agent uses this reference to prepare adoption. User setup begins with
[First use](../../QUICKSTART.md); the installed Skill owns the setup procedure.
The same contract serves new and existing projects after ordinary initialization.

## Adoption request

`signetum adopt preview --repository . --request <request.json> --output <plan.json>`
accepts:

- `manifest`: complete reviewed `signetum.toml` text.
- `retirements`: optional exact `{path, digest}` entries for known managed files.

Use manifest schema 4. Declare `signetum.engine_digest` from the prepared Skill's
`adopt inspect`, `[delivery] branch`, record roots, actual preparation, member,
batch and final commands, tool identities, locks and additional validation inputs.
Architecture is optional. Outside-world checks remain final-only. The normal
payload is only `signetum.toml`; application metadata, Agent entry files, Justfile
and environments remain untouched. Explicit retirement refuses drift or unknown
files. It offers no old execution fallback.

Preview records the exact base, before/after bytes and runtime identity.
`signetum adopt apply --repository . --plan <plan.json> --expected-plan <digest>`
requires that exact approved plan and unchanged targets. Ordinary write errors
roll back that invocation; abrupt interruption requires inspection and a fresh
preview. Neither operation executes application commands or creates approval.

## Existing runner proposal

Optional `python-existing@1`, `node-existing@1` and `rust-existing@1` adapters
propose bindings without installing tools or detecting languages from paths.
Other languages bind commands directly through the same validation schema.
`signetum adopt runner --request <request.json>` accepts, for example:

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
