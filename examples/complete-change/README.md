> This read-only example preserves the historical Review/Specification/Plan
> format. New work uses `just change-open` in a registered member workspace to
> create one `change.toml`; see the [current quickstart](../../QUICKSTART.md).

# Complete change example

This directory is a teaching artifact, not a second active change authority.
It demonstrates one requirement clause, its approved observable behavior, and
the Plan obligation that closes coverage.

- [`review.yaml`](review.yaml) records what the human requested.
- [`specs/greeting.yaml`](specs/greeting.yaml) owns the public behavior.
- [`plans/greeting.md`](plans/greeting.md) defines implementation and evidence.

Preserve this historical example for legacy reading. For new work, generate one
change record through the current tool rather than copying this multi-file
structure. Active work belongs under the configured `changes/` authority.
