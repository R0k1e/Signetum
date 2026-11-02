# Release Signetum

`main` is the product source declared by repository delivery policy. One tag
identifies the standard Skill, package and schemas. Package and Skill share the
product version; schemas change only with their formats.
Release metadata binds their actual versions and digests to the exact source.
Only the current metadata format is supported. Internal scaffolding has no
independent release. Never move a published tag or replace its artifacts.

## Prepare

Use semantic product versions: major for incompatible public contracts, minor for
normal feature releases, patch for compatible fixes. Do not advance the major
number for an internal cleanup or each development batch. Internal schema
revisions follow actual serialized format changes rather than product releases.
Before 1.0, a minor release may refine unstable contracts; state incompatible
schema changes explicitly in its release notes.

Use the toolchain in `mise.toml` and the setup in [Contributing](../../CONTRIBUTING.md).
The complete native acceptance suite needs Node/npm and Rust/Cargo as well as
Git, Python, uv and Mise/Worktrunk. These are repository development dependencies,
not additional application-language requirements for Skill users.

Before delivery, update the package version and release notes, build the nested engine and complete the normal batch final review. Release preflight requires package and Skill versions to agree with
`skills/signetum/scripts/engine/pyproject.toml`; choose an unused `v<version>` tag. Historical
RepoSeal tags remain unchanged. The 0.3.1 entry is a candidate until published. Keep its reviewed version section
in CHANGELOG.md concise and focused on user outcomes; do not maintain another
announcement with the same facts.

Deliver the reviewed source explicitly. Require successful CI for that exact
commit and verify the public Skill path and Pages deployment. CI and release
share one reusable validation workflow and the declared final gate, including
native acceptance and dependency audit. All Linux/macOS targets must pass and
combined project coverage must reach 90%; a partial host report is not a verdict. Hosted diagnostics issue no lifecycle receipt
and do not grant publication permission. Failure output is retained for seven
days; inspect the complete artifact when the bounded terminal preview is not enough.

## Distribution

The primary unit is the complete standard `skills/signetum` folder at an exact
GitHub tag, also provided as `signetum-skill-<version>.zip` with checksums. Its
instructions, engine source and runtime lock travel together. Exclude `.runtime`,
environments, bytecode and build output. The launcher prepares its own locked
noneditable environment once; no separate global engine installation is needed.
Internal wheel/sdist artifacts verify that boundary, rather than adding another
user setup route. Consumers need no upstream checkout for daily work.

## Publish and verify

Obtain explicit authorization naming the exact delivered source and version.
Create an annotated tag for that commit and push only that tag. The release
workflow checks out the triggering commit, prepares declared tools, verifies
policy-bound source/tag eligibility and runs the complete diagnostic gate. After all targets and coverage pass, a separate publishing job verifies the
primary target's checksums and publishes the Skill archive, internal wheel/sdist,
source/component metadata, extracted `RELEASE_NOTES.md` and `SHA256SUMS` to GitHub.
The notes come from the matching reviewed CHANGELOG.md version section, travel
inside the checksum-verified artifact and supply the GitHub release body.
Publication does not regenerate a description from commit history.

Download the public artifacts and verify checksums, tag/source and component
identities. Install the complete standard Skill from that tag or archive and run its explicit
setup in an isolated acceptance area. Complete reviewed adoption and a small authorized change
through ready in both a new project and an existing repository; preserve its
application metadata and runner.
Do not claim public installation from a local build or a successful preflight.

If publication stops partway, inspect existing tag and artifact identities before
retrying. Do not rerun a successful publication or rebuild under the same released
version. Complete only the missing authorized destination using the verified
artifacts, or prepare a new version when their identity cannot be established.
