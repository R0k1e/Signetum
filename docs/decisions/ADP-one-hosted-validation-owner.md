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
it. Publication permissions and source/tag preflight stay in the release workflow.

The owner requested a coherent, concise, releasable repository after this audit.
Separate hosted check lists would preserve the observed drift; invoking lifecycle
final in CI would incorrectly require private workspace and approval state.
Revisit only if measured platform needs require partitioning the same graph.
