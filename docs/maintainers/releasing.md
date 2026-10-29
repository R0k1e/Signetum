# Maintainer release guide

## Source and artifacts

`engine` owns the Signetum package, bundled `repo-dev` Skill, schemas and source
Template. `main` is the rendered clone-ready Template, with its own
`template_version`; it is never the source of an engine package release.
A GitHub tag `v<engine-version>` identifies one delivered engine commit. Package,
Skill and schema identities may have different versions; release metadata records
their actual identities and the full Skill payload digest. Do not retag historical
RepoSeal releases or rename their published files.

Skill installers can use `skills/repo-dev` at that exact tag or commit. The wheel
includes the same folder. No separate Skill release pipeline or installer is
needed. Use the canonical repository `R0k1e/Signetum` for source, releases and
Pages; the old repository URL redirects.

## Prepare and verify

Deliver the release change through the normal reviewed engine batch. Confirm the
chosen source is present in remote `engine`, ordinary CI passed for that exact
source, and versions and `CHANGELOG.md` describe the intended release. Record the
release date through a normal change before tagging. Check PyPI trusted publishing
and GitHub repository metadata. Neither a ready member nor preflight authorizes
publication.

From a clean checkout of the exact delivered source, with the locked environment:

```sh
git fetch --no-tags origin refs/heads/engine:refs/remotes/origin/engine
uv sync --locked --all-extras --dev
uv run signetum release preflight --source "$(git rev-parse HEAD)"
```

Preflight checks clean exact HEAD, membership in delivered engine history and
actual component versions. It reads no machine-local validation receipt and does
not claim that CI, final validation or human approval passed. The normal delivery
protocol owns final validation; hosted release validation runs independently on
the same source. An unavailable engine ref is a refusal, not a fallback to main.

## Publish only when explicitly authorized

A maintainer instruction must name the exact source and semantic version. Create
an annotated `v<version>` tag for that source and push only that tag. The workflow
checks out `${{ github.sha }}`, fetches engine, and invokes the same preflight with
`--tag <version-tag>` to verify tag/version/source agreement before building.
It runs the declared release checks, publishes the exact wheel and sdist through
PyPI trusted publishing, and creates a GitHub Release with those artifacts, the source/component
metadata and checksums. Authentication or validation failure must fail publication.

Do not reuse another commit's build, move an existing tag, or upload substitute
artifacts. Engine delivery, Template rendering, Pages deployment and package
publication are distinct actions; authorizing one does not authorize the others.

## Verify the published path

Download the release wheel, sdist and `SHA256SUMS`; verify hashes, source and
package-index identity. Install the Skill from the exact public release source
in a clean agent environment, install that engine once for an existing repository,
and complete the Quickstart through a small real change and ready. Separately
render the intended Template revision to main through reviewed delivery and check
its new-repository Quickstart. Existing consumers adopt updates explicitly.
