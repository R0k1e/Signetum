# Python and uv policy

Use `uv sync --locked`, `uv run`, and `uv build` as the only Python environment,
execution, and build authority. Test public behavior before implementation and
inspect built wheel contents.


Use `just test <paths-or-native-test-options>` for explicit development feedback.
It delegates to the declared shard through the same allocator and supervisor as
ready and CI, without a readiness receipt. Prepare the environment with uv first;
installed-artifact tests also require the current `uv build --project skills/signetum/scripts/engine --out-dir dist --clear` output. Do not start
several full suites concurrently or add inner worker counts independently of the
enclosing allocation. Preserve unique mutable repositories, ports, scratch and
reports; reuse only successful immutable preparation. A failure is never a
reusable cached observation.

Read phase durations and actual allocation before changing worker ceilings,
fixture scopes or scheduling. Compare on the same host and corpus. Measurements
are diagnostic evidence, not permanent node-count or time budgets. Keep reports
in ordinary logs and significant conclusions in the existing change journal.

Use changed only to explain the plan; do not precede ready with a duplicate suite.
New tests state their distinct risk and use the cheapest effective boundary.
Optional selection, scheduling and CI splitting keep source-bound configuration
and do not alter first-failure or final-completeness requirements.
