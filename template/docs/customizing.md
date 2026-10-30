# Customizing this repository

Keep Signetum's workflow authorities separate from application authorities.
Add product source, tests, and deployment configuration at paths named in
`docs/ARCHITECTURE.md`; then bind the real targeted and final validation in
`.agents/repo-dev/repo.yaml`.

Repository-specific rules belong in a small referenced policy document, not in
the reusable lifecycle. Configure enabled language profiles, impact rules,
named gates, and final shards in `signetum.toml`. Profiles compose, so a
repository may use Python, TypeScript, Rust, or several languages without
changing lifecycle commands. A later lifecycle improvement is adopted manually
as an ordinary reviewed architecture or process change; there is no package
upgrade.

`signetum.toml` contains only executable runtime and validation settings.
`.agents/repo-dev/repo.yaml` contains repository paths, Agent policy routing,
and delivery settings. In a registered member workspace, start a draft with
`just change-open <kebab-name>`;
the command creates one draft change record under the declared change root.

## Checks which depend on the outside world

A shard whose verdict depends on state outside the observed tree, such as the
dependency audit, declares `evidence = "world"` and a `findings_command` that
emits the Signetum findings document. Such a shard never enters the member gate:
member closure stays a function of the tree, so a newly published advisory
cannot block an unrelated member.

When the repository decides to carry a reported finding, add a tracked waiver
under `changes/<change-id>/waivers/` naming the shard, the exact findings, the
reason, the approver, and a mandatory `expires` date. The gate then records the
shard as `waived` rather than `passed`, and an expired waiver fails the gate
instead of passing quietly.

## Existing language runners

Optional `python-existing@1`, `node-existing@1` and `rust-existing@1` bindings
preserve an existing test command and its declared tool identities. Generate a
proposal with `just protocol runner --request <request-path>`, then merge it
through an approved local adoption change. Preserve core contract, preparation,
batch and final-only checks. The generator never installs dependencies, edits
application metadata or runs the proposed command. Python remains the protocol
host, independently of the application's language and project files.
