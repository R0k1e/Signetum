# One hosted validation owner

Status: Accepted
Review date: 2026-10-30
Supersedes: None
Superseded by: None

CI and release maintained independent command lists and tool preparation. The
release path omitted Mise despite native workspace acceptance needing it;
handwritten lists also omitted checks in the declared complete graph.

Use the existing diagnostic gate executor through `protocol test --gate`, with
strict declared commands and no readiness or delivery receipt. Keep single-shard
native arguments for focused feedback. One local hosted action owns environment
preparation, complete validation and failed-output upload; CI and release compose
it. The release workflow requests source/tag preflight; publication permissions stay
there.

The owner requested a coherent, concise, releasable repository after this audit.
Separate hosted check lists would preserve the observed drift; invoking lifecycle
final in CI would incorrectly require private workspace and approval state.
Revisit only if measured platform needs require partitioning the same graph.

The standard Skill and GitHub release artifacts are the primary distribution
route. PyPI is explicit opt-in, so a package-index account is not a prerequisite
for the first Skill release. Both routes use the same verified artifacts.

[The first Linux run](https://github.com/R0k1e/Signetum/actions/runs/41008832516)
passed every test but measured 89.73% whole-source coverage:
Darwin native observation was not executable there. Retain native acceptance on
both hosts and all Python targets, then combine complete source-relative coverage
and enforce 90% once. Partial platform data is not a project verdict. Local gates
retain 90%. A reusable hosted workflow owns the target set and completeness check;
release publishes its verified artifact only after that entire workflow passes.
This avoids artificial platform mocks, a lower project threshold or divergent
release checks. Superseded CI runs may cancel; publication never does.
