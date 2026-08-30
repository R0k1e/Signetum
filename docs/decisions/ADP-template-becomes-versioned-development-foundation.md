# The Python template becomes a versioned development foundation

Status: Accepted
Review date: 2026-08-28
Supersedes: None
Superseded by: ADP-foundation-is-a-standalone-template.md

## Context

This repository began as a Python application template. Its current product
surface is placeholder application code, a one-time rename script, Python-stack
defaults, CI that commits automatic fixes, CI that merges branches into
`main`, and a release workflow that publishes the generated application.

PyLM has since developed a broader repository-development lifecycle: routed
policy, isolated worktrees, specifications and plans, architecture decisions,
validation receipts bound to exact commits, explicit batch assembly, frozen
final validation, explicit delivery, and recovery constraints. Copying those
mechanisms independently into repositories would create drifting authorities.

A shared foundation must not own any downstream product fact. It must also not
change a downstream repository merely because its own default branch moved.

## Decision

This repository becomes the sole versioned upstream authority for generic
repository-development mechanisms.

It publishes three identities as one compatible release:

1. a Python distribution containing typed manifests, schemas, validators,
   evidence interfaces, and a check-only CLI;
2. a `repo-dev` Codex skill with generic lifecycle guidance;
3. a schema/profile bundle for repository specialization.

A downstream repository pins an immutable release version and artifact digest.
It owns its requirements, specifications, plans, architecture, decisions, test
selection, receipts, delivery state, and the adapter that binds its public
operations to foundation mechanisms.

Technology-specific rules are opt-in profiles. The generic foundation does not
require every consumer to use Pydantic, Lagom, Hydra, transitions, returns,
uvloop, Node, Rust, GitHub Actions, Worktrunk, or Just.

The former placeholder application, rename initializer, auto-fix CI, auto-merge
CI, and application-template release are replaced rather than retained behind
compatibility aliases.

Ordinary validation is check-only and observes one exact commit. Publishing,
remote renaming, tag pushing, merging, and branch deletion are separately
authorized external mutations.

The foundation uses semantic major/minor/patch releases and independently
versioned manifest, change, and receipt schemas. A downstream refuses an
unsupported schema instead of applying a fallback interpretation.

## Rejected alternatives

### Continue copying files from PyLM

Rejected because two repositories would own the same checker and skill behavior,
and fixes could land in one without the other.

### Consume the foundation default branch

Rejected because the same downstream commit could pass or fail on different
days and receipts could not reproduce their tool identity.

### Preserve template and foundation modes together

Rejected because initialization, application packaging, and reusable lifecycle
mechanisms have incompatible authorities and release contracts.

### Use a Git submodule as the primary integration

Rejected because clone completeness, worktree ownership, CI initialization, and
receipt identity become more fragile. A vendored snapshot remains a temporary
fallback only if versioned skill installation is unavailable.

### Move downstream plans and decisions upstream

Rejected because they are product facts and authorizations, not generic
mechanisms.

## Consequences

- The next supported product release is a breaking major foundation release.
- Existing Git history and the License remain.
- The repository needs its own safety contract, architecture entry, manifest,
  change package, validation authority, and explicit delivery protocol.
- PyLM adoption is a separate downstream decision and delivery.
- Old template users remain reproducible through an immutable legacy tag, but
  there is no runtime compatibility mode.
- Foundation upgrades become reviewable dependency changes instead of file
  synchronization.

## Enforcement

- CI checks out and validates one exact commit and has no branch-write
  permission during ordinary validation.
- Release metadata binds package, skill, schema versions, and digests.
- Manifest validation rejects moving branch identities and unsupported schemas.
- Repository tests reject PyLM-specific paths or selectors in generic assets.
- Downstream receipts bind the selected foundation identity.

## Workflow cost

| Measure | Before | After |
| --- | ---: | ---: |
| Success-path commands | Template-specific and implicit | Repository-bound, explicit |
| Success-path full gates | Multiple unbound workflow jobs | One frozen final authority per repository |
| New persistent authorities | 0 reusable foundation authorities | 1 versioned foundation release |
