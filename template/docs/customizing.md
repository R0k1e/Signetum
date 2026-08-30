# Customizing this repository

Keep RepoSeal's workflow authorities separate from application authorities.
Add product source, tests, and deployment configuration at paths named in
`docs/ARCHITECTURE.md`; then bind the real targeted and final validation in
`.agents/repo-dev/repo.yaml`.

Repository-specific rules belong in a small referenced policy document, not in
the reusable lifecycle. Upgrade RepoSeal by reviewing a released version,
changing the exact pin in both `reposeal.yaml` and `Justfile`, and validating
the change like any other architecture or process decision.
