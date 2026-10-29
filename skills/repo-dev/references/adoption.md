# Explicit local adoption

This skill is a distribution unit for instructions and a local launcher. The
repository owns its runtime and bindings. Install this `repo-dev` folder with
the coding agent's standard skill installer; installation does not modify a
project or adopt new policies.

Before commands, distinguish three cases:

- Skill only: instructions are installed; no repository runtime is implied.
- Existing repository: Git and a host Python 3.12+ are needed. Install one exact
  reviewed Signetum engine with uv to prepare adoption. The agent obtains an
  available release or source commit and constructs the request; the owner
  reviews the preview, not JSON syntax. Workspace operations also need the
  repository-declared Mise and Worktrunk setup.
- Adopted repository or rendered Template: use its local runtime and declared
  tools. Normal development needs no globally installed Signetum engine; the
  application can retain Node, Rust or another runner.

Check tools without installing or trusting configuration automatically. If a
prerequisite is missing, identify the exact missing tool and the next setup
step from the [first-use guide](https://github.com/R0k1e/Signetum/blob/engine/QUICKSTART.md).
An unavailable source revision needs an available reviewed revision; never
substitute an old release or download an unreviewed latest version silently.

When adoption is requested, read the maintained first-use and adoption guides.
Use `adopt inspect` through this Skill launcher to inspect without mutation.
It requires an installed reviewed engine, not an adopted repository. Prepare a
request with the existing runner, tools, inputs and merged policy; `adopt preview`
exports the local runtime and returns exact file changes and a plan digest.
Show that preview and resolve missing prerequisites. Apply the approved plan
only when authorized. A changed source, target or runtime requires a fresh
preview; do not force it. Application Justfile and metadata remain owned by the
consumer. No adoption step executes project commands or creates approval.

After adoption the launcher uses `.agents/repo-dev/run protocol`; existing
`just protocol` consumers keep their binding. Use the repository's local
lifecycle launcher for workspaces and delivery. The maintained engine source is
[Signetum](https://github.com/R0k1e/Signetum/tree/engine); first use is documented
[here](https://github.com/R0k1e/Signetum/blob/engine/QUICKSTART.md).

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

Historical working sets are read and organized by the agent, using ordinary
source references and reviewed decision proposals. Do not configure a document
parser or infer approval from a table. Structured test selection is optional:
without an explicit provider, readiness runs all declared member checks without
impact narrowing or inherited test skips. Changed only explains selection;
explicit test diagnostics run the named shard. Final remains complete.

Bind local and CI test diagnostics to the repository's declared test shard and
one allocator. Keep required preparation explicit. Use one locked static-tool
version and avoid repeating the same static check inside another gate. Batch
admission and conflict continuation run preparation and batch static checks;
complete final validation judges the assembled result. Keep current how-pages
self-contained and historical reasons in the existing decision/change history.

Treat installation and first use as part of acceptance. Exercise the installed
launcher and literal native arguments, not only internal modules. Prefer a
verified development problem and the consumer's existing tools over additional
workflow machinery; maintenance and review burden are part of the cost.
