# Customizing this repository

Keep RepoSeal's workflow authorities separate from application authorities.
Add product source, tests, and deployment configuration at paths named in
`docs/ARCHITECTURE.md`; then bind the real targeted and final validation in
`.agents/repo-dev/repo.yaml`.

Repository-specific rules belong in a small referenced policy document, not in
the reusable lifecycle. Configure enabled language profiles, impact rules,
named gates, and final shards in `reposeal.toml`. Profiles compose, so a
repository may use Python, TypeScript, Rust, or several languages without
changing lifecycle commands. A later lifecycle improvement is adopted manually
as an ordinary reviewed architecture or process change; there is no package
upgrade.

`reposeal.toml` contains only executable runtime and validation settings.
`.agents/repo-dev/repo.yaml` contains repository paths, Agent policy routing,
and delivery settings. Start real work with `just change-open <kebab-name>`;
the command creates a draft under `changes/` and never edits `examples/`.
