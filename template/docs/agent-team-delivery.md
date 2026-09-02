# Agent-team delivery

Assign each independently implementable plan to a separate branch and
worktree. A task brief names its specification, approved base, owned paths,
observable acceptance criteria, and targeted validation. Agents must not edit
the delivery worktree or silently broaden scope.

Member checks are targeted and may run repeatedly. Complete validation runs
once after named members have been merged into a frozen batch. Delivery binds
the expected base, batch tip, validation receipt, admitted members, and
declared plans so the shipped content is inspectable.

## Human control and execution deviations

Before implementation, the Agent presents the approved outcomes, non-goals,
acceptance evidence, and autonomy boundary. During implementation, every
discovery that may affect the approved commitment, a durable authority, or the
delivery explanation is recorded through the repository-owned support runtime:

```text
uv run --no-project python .agents/repo-dev/runtime/deviations.py approval --change <change-id>
uv run --no-project python .agents/repo-dev/runtime/deviations.py record ...
uv run --no-project python .agents/repo-dev/runtime/deviations.py resolve ...
uv run --no-project python .agents/repo-dev/runtime/deviations.py status --change <change-id>
```

The runtime owns `.git/signetum/changes/<change-id>/deviations.jsonl`; Agents
never edit it directly. Ordinary implementation narration does not belong in
the ledger. `final` is still check-only: it refuses unresolved deviations and
returns the structured inputs for a concise delivery review. That review
compares every approved commitment with delivered behavior and evidence, and
separately discloses deviations, authority updates, extra work, and unfinished
work before explicit delivery.
