# Inventory an existing decision working set

A repository may keep accepted constraints outside its decision log. Explicitly
opt in that exact source through the committed runtime manifest:

```toml
[[migration.sources]]
id = "constraints"
path = "docs/architecture/constraints.md"
format = "markdown-constraints@1"
```

This format reads Markdown tables with the exact headers `do_not` and `because`.
It preserves the cell text, including any reopen condition in `because`, the
nearest heading, original line range, introductory context and Git blob. It does
not infer a missing decision identifier or approval. Fenced examples are not
rules. Incomplete rows and unrecognized tables remain review issues.

Run the repository's `protocol migration inventory` utility. Without declarations,
the existing version-one inventory remains unchanged. Opted-in sources produce a
version-two inventory with `working_sets`; their status is
`declared_working_set`, distinct from accepted decisions. Missing, uncommitted,
redirected or symlink sources refuse. Original accepted files are never edited.

A mapping proposal names the inventory digest, exact source commit, explicit
topic and stable clause identity. For this format each source span selects one
complete row. Preserve its prohibition as the clause statement and its complete
basis as the rationale; a migration preview cannot silently drop a reopen
condition or weaken the rule. Later amendments use ordinary approved decisions.

`protocol migration preview --proposal <path>` displays the original row beside
the candidate. It always remains unapproved. `unmapped_rows` identifies complete
working-set rows not selected by a partial proposal; `unmapped` identifies sources
not selected at all. Remaining source issues stay visible. Changed source bytes,
bindings or inventory identity require a fresh review.

Accept any resulting proposal through the repository's normal approval and
history authority. Discovery alone never populates the current decision working
set. Relevant historical rules continue to apply until explicit adoption, and
existing accepted files remain read-only historical evidence.
