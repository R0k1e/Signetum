# Repository foundation responsibilities

Within this template, `development_foundation` owns generic parsing, package resources,
profile composition, evidence protocols, and the check-only `foundation` CLI.
It contains no downstream application path, branch, selector, or delivery
policy.

The repository specialization manifest owns local paths and selects exact
profile identities. Profiles declare dependencies and authorities; composition
rejects unsupported identities, missing dependencies, and duplicate authority
ownership. Repository adapters implement evidence protocols, so generic
mechanisms pass typed values without inferring repository facts. After GitHub
creates another repository from this template, that repository owns its copy
and evolves independently; this template supplies no synchronization channel.

The public product surface is rooted at `README.md`. `QUICKSTART.md`, focused
concept and workflow guides, the complete-change teaching artifact, and public
governance files explain current contracts without becoming additional
execution authorities. Repository validation checks that those required assets
and their local Markdown references remain present.
