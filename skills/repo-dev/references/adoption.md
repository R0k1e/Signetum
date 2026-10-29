# Explicit local adoption

This skill is a distribution unit for instructions and a local launcher. The
repository owns its runtime and bindings. Install this `repo-dev` folder with
the coding agent's standard skill installer; installation does not modify a
project or adopt new policies.

When adoption is requested, inspect the existing architecture, language runners,
workspace policy and delivery authority. Prepare a reviewable local change that
binds the protocol to those existing tools. The standard layout is `SKILL.md`,
conditional `references/` and `scripts/`; the maintained source is
[Signetum](https://github.com/R0k1e/Signetum/tree/engine/skills/repo-dev).
The engine exports its local utilities through `just protocol`; a rendered
repository runs the same generated local implementation locally.

For existing history, run `migration inventory`, then `migration preview` with
explicit source spans, stable clause IDs and topic context. Preserve ambiguous
mappings and original accepted files. A preview never grants approval, revives
a replaced rule or declares a whole document migrated from a few selected lines.
Accept reviewed mappings through the repository's change and decision authority.

Keep one record per change and one append-only significant journal. Read the
current decision projection before work and original rationale only on demand.
No remote ledger, cross-machine service, automatic update, account system or
additional application test runner is needed. Later extensions use the same
source and explicit repository adoption boundary.

For an existing application runner, `runner --request <disposable-request-path>`
emits an unapproved binding proposal. Its request names `language` (`python`,
`node` or `rust`), the exact `command` argv, `tools` with names and
`identity_command` argv, and an optional positive `timeout_seconds`. It executes
nothing and installs nothing. Merge its application declaration deliberately;
preserve existing core, preparation, batch and final-only checks and declared
inputs. Profile selection alone never activates omitted commands. The host
protocol interpreter does not impose Python project metadata on the application.
