# Template authority cleanup plan

Status: approved
Specification: `changes/template-authority-cleanup/specs/template-authorities.yaml`
Base: `engine@395a278cbe3c74ba1185c3841fe0de951c7922b2`

| Obligation | Clauses | Outcome |
| --- | --- | --- |
| CONFIG | CLEAN-001 | Move repository path ownership to repo.yaml and keep runtime gates in reposeal.yaml. |
| DECISIONS | CLEAN-002 | Materialize the decisions authority in the empty Template. |
| SCAFFOLD | CLEAN-003 | Add a non-lifecycle change authoring utility and behavior tests. |
| DOCS | CLEAN-001, CLEAN-002, CLEAN-003 | Explain the boundaries without adding another general guide. |
