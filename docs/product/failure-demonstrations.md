# Try the protocol's failure boundaries

These commands run from the engine source checkout with its locked development
environment (`uv sync --locked`) and Git available. They use disposable fixture
repositories; they do not publish to GitHub or deliver this checkout. A passing
negative test means the operation refused the invalid state as asserted.

## Minimal example: one approved change

In a repository that has explicitly adopted the protocol, open a member with
`just workspace-open <branch> <exact-base>` and enter the returned worktree:

```sh
just protocol current
just change-open add-health-endpoint
just protocol view changes/add-health-endpoint/change.toml
```

Fill the generated draft with one observable requirement: an existing health
endpoint returns the repository's agreed successful response. Name its behavioral
test, execution steps and autonomy boundary. Show the generated view to the
owner; record actual confirmation of the exact contract digest and commit that
approval before implementing. Do not manufacture an approval for the example.
After implementation and its test are committed, `just ready` must validate that
exact tip. Editing afterward requires a new commit and fresh readiness.

The existing [Quickstart](../../QUICKSTART.md) continues through an explicit
batch and delivery. The commands above assume adoption and are not an installer.

## 1. A requirement has no implementation owner

```sh
just test -q tests/unit/test_change_record.py::test_steps_cannot_omit_invent_or_duplicate_requirement_ownership
```

The record reader refuses omitted, invented and duplicate step ownership. This
shows structural accounting of recorded requirements. It cannot detect an
unrecorded sentence left in a conversation or prove that a named test is adequate.

## 2. Green evidence belongs to an older commit

```sh
just test -q tests/test_batch_admission.py::test_reworded_member_requires_fresh_exact_tip_evidence
```

The fixture creates readiness evidence, changes the commit identity while
retaining the same tree, and attempts admission. Admission refuses the stale
proof. This isolates exact-tip binding using constructed evidence; it does not
claim to exercise every validation command or evidence-inheritance case.

## 3. Publication fails, then resumes

```sh
just test -q tests/integration/test_delivery_recovery.py::test_rejected_push_keeps_target_at_base tests/integration/test_delivery_recovery.py::test_published_delivery_resumes_local_move
```

A real local bare Git remote rejects publication: the local target stays at its
base. Removing the fixture hook permits an ordinary retry. A second scenario
interrupts after remote publication and verifies that retry completes the local
move to the already published identity. Both engine and generated-runtime
frontends are exercised.

These delivery tests construct qualified input and substitute attestation,
member provenance and cleanup boundaries to isolate publication recovery. They
are not a full end-to-end qualification demonstration, and perform no network
publication. Their value is the asserted failure and recovery behavior, not a
production throughput or reliability measurement.
