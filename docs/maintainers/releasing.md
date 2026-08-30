# Maintainer release guide

Releasing is separate from development delivery. A ready member, integrated
batch, passed final gate, or commit on `main` does not by itself authorize a
version tag, package publication, or GitHub Release.

## Preconditions

Before requesting publication:

1. Confirm the release change was delivered through the repository's exact
   batch-delivery authority and that remote `main` equals the delivered commit.
2. Confirm the version in `pyproject.toml`, package `__version__`, packaged
   skill metadata, schemas, and `CHANGELOG.md` describe one compatible release.
3. Move the release section from `Unreleased` to its actual release date as a
   governed change and deliver it before tagging.
4. Confirm ordinary CI passes for the exact delivered commit.
5. Confirm the PyPI project has GitHub Actions trusted publishing configured for
   this repository and release workflow. Missing authentication must fail; the
   workflow must never report a skipped publication as success.
6. Confirm the GitHub repository description, topics, homepage, Template flag,
   license, and social preview describe the current product.

Recommended repository description:

```text
DevLoom weaves requirements into verified releases with repository-aware Agents, isolated parallel work, behavior tests, and explainable delivery.
```

Recommended repository name:

```text
devloom
```

Recommended topics:

```text
ai-agents, agentic-development, developer-tools, github-template,
requirements-traceability, git-worktree, continuous-integration, python
```

## Publication

Publication requires an explicit maintainer instruction naming the exact
delivered source and semantic version. Create an annotated `v<version>` tag only
for that source and push that exact tag. The tag-triggered workflow checks out
`${{ github.sha }}`, prepares the locked environment, builds the wheel and
source distribution, reruns the release validation graph, writes checksums,
publishes through PyPI trusted publishing, and creates the GitHub Release with
the same artifacts.

Do not manually upload a different local build, reuse an artifact from another
commit, move an existing version tag, or publish from a dirty worktree.

## Confirmation

After the workflow completes:

- verify the GitHub Release tag and target commit;
- download the wheel, source distribution, and `SHA256SUMS` and verify them;
- verify the package index reports the same version and artifact digests;
- create a clean repository from the Template and complete the documented
  Quickstart through validation;
- record any failure as a new governed Review rather than rewriting the
  released tag or artifacts.

The Template repositories created before this release remain independent and
receive no automatic update.
