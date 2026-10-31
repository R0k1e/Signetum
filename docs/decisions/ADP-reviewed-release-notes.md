# Publication uses reviewed version notes

Status: Accepted
Review date: 2026-10-31
Supersedes: None
Superseded by: None

The owner directs release material preparation ahead of publication. The matching
version section of CHANGELOG.md owns public release copy. The validated artifact
contains an extracted RELEASE_NOTES.md covered by its checksum manifest. Publication
uses that exact file; it does not generate a second description from commit logs.

This keeps review focused on user outcomes and essential upgrade information.
GitHub-generated notes would bypass curated copy and expose internal iteration
as release messaging. Keep existing README/site/branding and avoid a separate
announcement document with the same facts. Reopen when a distinct distribution
channel requires genuinely different copy. Tag and publication authority remain
separate from preparing and delivering the source.
