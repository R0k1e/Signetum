# Release Signetum

The product source is `main`, declared by `delivery.branch` in repository policy.
The package bundles the same `skills/signetum` folder users install through their
agent. Skill, package and schema versions may differ; release metadata binds their
actual identities to one exact delivered source through metadata schema v2.
Only the current metadata schema is shipped and supported. Internal scaffolding has no
independent public release. Historical tags and artifacts remain immutable.

## Prepare the exact source

Deliver the reviewed change through the normal batch protocol. Confirm ordinary
CI passed for that exact source, versions and `CHANGELOG.md` describe the intended
release, and PyPI trusted publishing and repository metadata are configured.
Readiness or preflight alone never authorizes publication.

From a clean checkout with the locked environment:

```sh
uv sync --locked --all-extras --dev
SOURCE_BRANCH="$(uv run python -c 'from pathlib import Path; from signetum.policy import delivery_policy; print(delivery_policy(Path.cwd()).branch)')"
git fetch --no-tags origin "refs/heads/$SOURCE_BRANCH:refs/remotes/origin/$SOURCE_BRANCH"
uv run signetum release preflight --source "$(git rev-parse HEAD)"
```

The same preflight runs in release CI and additionally checks `--tag`. It verifies
source eligibility and component identity; it does not substitute for final,
CI or publication approval and reads no machine-local final receipt.

## Publish when explicitly authorized

The maintainer names exact source and version. Create an annotated `v<version>`
tag for that source and push only that tag. The workflow checks out the triggering
commit, fetches the policy-declared source branch, preflights, builds and runs the
declared checks, then publishes exact wheel/sdist and GitHub Release artifacts.
Source/component metadata and checksums accompany the artifacts. Never move a
published tag, reuse another source's build or skip failed authentication.

Verify downloaded hashes, tag/source and package-index identity. Install the
standard Skill and fixed-version setup tool in an isolated project, adopt it and
complete a real change through ready. No template promotion or separate Skill
release pipeline is needed. Source delivery, site deployment and package
publication remain distinct authorized actions.
