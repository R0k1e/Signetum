# Work and validation

Use the registered member workspace, immutable base and repository environment.
Find and extend the existing implementation owner. Reproduce changed behavior
through its public boundary and validate the approved contract with the existing
runner. Without a selection provider, run the full declared member gate. An
explicit provider may select checks; this skill does not select an application
language or replace its test system.

Use `record` for a finding that changes implementation, authority, scope or the
delivery explanation. Use `resolve`, `retract`, `reconcile` or `retire` for its
standing answer and accepted decision changes. Each mutation takes a structured
`--request` and the `--expected-history` returned by `current` or `status-all`.
Requests bind the expected approval digest. On a stale identity, inspect the
current state and reassess the request; never force a replacement or edit JSONL.
Ordinary command output stays in local logs, not a handwritten work report.

A minimal `record` request has this shape; replace the identities and digest
with the current approved values. Keep request files disposable; the tool owns
the durable journal.

```json
{
  "id": "change-id/observation-1",
  "change_id": "change-id",
  "approval_digest": "sha256:<approved-contract-digest>",
  "operation": "record",
  "reason": "Why this finding matters to the approved outcome.",
  "observations": [{
    "id": "change-id/finding-1",
    "requirements": ["REQ-001"],
    "summary": "The significant finding.",
    "reason": "Its supporting basis.",
    "evidence": ["path/to/existing-evidence"]
  }]
}
```

For `resolve`, use a fresh transaction ID, no new observations, and
`resolutions` entries with `id`, exact observation `target`, `status`, `reason`
and `evidence`. Status is `resolved`, `rejected` or `deferred`; a deferral also
names `followup` as `change-id#REQ-ID` and requires the exact approved transfer.
A `retract` entry names `id`, `target`, `resolution_id` and `reason`.
`reconcile` combines changes atomically; its `decisions` must exactly match the
accepted contract proposals. `retirements` likewise match the contract's exact
approved evidence-retirement proposals. Each operation uses a fresh namespaced
ID and the same approved digest; inspect `--help` for command arguments.

Commit significant source events before validation freezes the source. Run the
repository's targeted checks during work and its member gate for ready. A first
failure remains failed even when a diagnostic retry passes; after fixing it,
run ordinary validation again. Process settlement checks only positively owned
jobs and refuses successful commands that leave owned children behind.

Preserve unrelated files and processes. Stop at a clean ready unless integration
or delivery is authorized. Validation never appends its own success to source.
