# Set up a new or existing project

Install the complete `signetum` Skill folder from an exact reviewed tag or commit.
It includes instructions, execution source and its dependency lock. Keep cwd in
the user's project and call `sh <skill-base-dir>/scripts/signetum ...`.

## Prepare the Skill once

Check Git, Mise, Worktrunk (`wt`), uv and host Python 3.12+. Report missing tools
and resolve setup explicitly. Honor the host's Mise trust decision; never trust
project configuration automatically. Run `setup` to select host Python 3.12 explicitly through Mise and create a locked environment
under the installed Skill's ignored `.runtime/` directory. `identity` reports its
code and dependency identities. No Signetum dependency belongs in the application's
production or development dependency groups. Application commands retain their
own environment; the engine environment is never prepended to their PATH.

Prepared operations use the Skill’s own bootstrap interpreter, regardless of
the application’s Python version or tool selection.
Ordinary operations refuse an absent, changed or incompatible environment with a
setup/update action. They never clone, install, sync or repair the Skill. Use a
writable complete Skill installation; do not copy its generated environment into
a distribution artifact. An upstream checkout is unnecessary for daily work.

## Review project bindings

For a new project, initialize its ordinary application files and Git history.
For an existing one, preserve tools, metadata, locks, entry files and decisions.
Both use the same adoption flow:

1. `adopt inspect` reports available tools and the engine digest without running
   application commands or reading/modifying Agent entrypoints.
2. Prepare one request containing the complete reviewed `signetum.toml` text.
   Bind the reported engine digest, delivery branch, record roots, actual tool
   identities, inputs and preparation/member/batch/final commands. Architecture
   is optional context. See the [binding contract](https://github.com/R0k1e/Signetum/blob/main/docs/guides/existing-runners.md).
3. `adopt preview --repository . --request <request.json> --output <plan.json>`
   captures the source and exact before/after bytes. Show the user that preview.
4. Apply the approved plan with `adopt apply --repository . --plan <plan.json>
   --expected-plan <digest>`. Changed source or targets require a fresh preview.
5. Commit through the project's existing process and exercise a small authorized
   change through `ready`. Preparation dependencies run before commands that need
   them; an environment failure is not permission to weaken application checks.

Normal adoption writes only `signetum.toml`. No required AGENTS/CLAUDE pointer,
architecture scaffolding, wrapper or copied engine is added. Legacy generated
files may be retired only through explicit exact-hash entries in the same reviewed
preview; changed and unmanaged files remain untouched. This retirement path does
not provide an old runtime fallback. Inspect interrupted application before retry.

## Continue and update

Use this installed Skill launcher for daily work. Project hooks remain active;
Signetum emits readable merge commits with structured provenance and does not
rewrite the project's commit convention. Updating the Skill or engine pin is a
later explicit reviewed operation. Historical decisions remain evidence; let the
agent retrieve and organize relevant context rather than forcing an archive
conversion or copying the full archive into each current view.

For an update, acquire the complete Skill folder at one reviewed exact tag or
commit into a new writable directory. Exclude the old `.runtime`; run explicit
`setup` and `identity` there before selecting it as the installed Skill. Keep the
previous installation available until verification succeeds and avoid replacing
files while commands are running. A Git pull in an upstream checkout does not
update an independently installed Skill. Setup prepares local dependencies; it
does not download newer Skill source.

Compare the new identity with each project's `signetum.engine_digest`. If engine
content changed, use the same inspect, preview and exact-plan apply flow in a
project change workspace, preserve all other bindings, then qualify and deliver
that update. If only launcher/instructions changed and the engine digest matches,
no project manifest change is needed. Verify the installed help, required commands
and a relevant project operation before removing the old installation. Existing
active workspaces and source-bound receipts are not automatically upgraded.
