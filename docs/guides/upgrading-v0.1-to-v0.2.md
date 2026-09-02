# Upgrade a copied v0.1 repository to the v0.2 protocol

Repositories created from Signetum own their runtime, so this is a reviewed
local change rather than an upstream pull or package upgrade.

1. Open a Change that records the protocol adoption and its repository-specific
   validation obligations.
2. Replace `signetum.yaml` with one `signetum.toml` v2 authority. Do not retain a
   fallback parser.
3. Select one or more profiles. `python-default@1` reproduces the maintained
   Python defaults; other languages contribute their own namespaced impact,
   gate, and shard declarations.
4. Replace handwritten worktree operations with the pinned Worktrunk backend
   and keep Mise as the external tool authority.
5. Convert only active Change packages to TOML. Treat delivered YAML packages
   as read-only history rather than rewriting provenance.
6. Adopt receipt v2 and invalidate every v0.1 member or final receipt.
7. Rename unaccepted decisions to `ADP-proposal-<slug>.md`; the next batch
   assigns formal numbers before final validation.
8. Exercise the eight public operations in a disposable repository, then admit
   and validate the upgrade as one explicit batch.

There is no compatibility shim between the two protocols. A repository that
needs staged adoption should keep the v0.1 runtime until its v0.2 Change can be
delivered atomically.
