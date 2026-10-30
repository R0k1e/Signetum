# A workspace owns its base

Status: approved
Specification: `changes/workspace-owns-its-base/specs/workspace-base.toml`
Base: `engine@b4e821136ba4409c08f458c805f2af2e26cd506b`

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| RECORD | BASE-001 | Write and read one workspace record under the existing state root. |
| ARGUMENT | BASE-002 | Remove the base argument from `changed` and `ready`. |
| BATCH | BASE-003 | Write a batch record and read every batch base from it. |
| PROVENANCE | BASE-004 | Keep the trailer as attestation, verify it at delivery, delete the history scan. |
| MIRROR | BASE-001, BASE-002, BASE-003 | Apply the same contract to the Template runtime and the shared vectors. |

RECORD precedes every other obligation. PROVENANCE lands last, once no caller
needs the scan it removes.
