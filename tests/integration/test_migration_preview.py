"""Legacy migration preserves source and exposes rather than guesses missing mappings."""

import importlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from change_fixtures import approve_change
from test_batch_admission import MANIFEST

from signetum.git import git_output
from signetum.serialization import contract_mapping


@pytest.fixture(params=["engine", "template"])
def migration(request, monkeypatch):
    if request.param == "engine":
        return importlib.import_module("signetum.migration")
    monkeypatch.syspath_prepend(
        str(Path(__file__).parents[2] / "template/.agents/repo-dev/runtime")
    )
    return importlib.import_module("_signetum_runtime.migration")


@pytest.fixture
def repository(tmp_path):
    git_output(tmp_path, "init", "-b", "main")
    git_output(tmp_path, "config", "user.name", "Migration test")
    git_output(tmp_path, "config", "user.email", "migration@example.invalid")
    (tmp_path / "seed").touch()
    git_output(tmp_path, "add", ".")
    git_output(tmp_path, "commit", "-m", "base")
    base = git_output(tmp_path, "rev-parse", "HEAD")
    approve_change(tmp_path)
    plan = tmp_path / "changes/example/plans/behavior.md"
    plan.write_text(plan.read_text().replace("Base: fixture", "Base: " + base))
    decision = tmp_path / "docs/decisions/AD-1.md"
    decision.parent.mkdir(parents=True)
    decision.write_text(
        "# Validation\n\nStatus: Accepted\n\n## Decision\n"
        "Keep the first failure failed.\nKeep ordinary logs local.\n"
    )
    git_output(tmp_path, "add", ".")
    git_output(tmp_path, "commit", "-m", "retain legacy authorities")
    return tmp_path


def test_inventory_retains_source_claims_acceptance_and_base_without_writing(repository, migration):
    before = git_output(repository, "status", "--porcelain")
    result = migration.inventory(repository)
    assert result.commit == git_output(repository, "rev-parse", "HEAD")
    assert len(result.documents) == 4
    assert (
        result.reviews[0].value.clauses[0].statement
        == "The member implements the approved behavior."
    )
    assert result.requirements[0].acceptance_indices == (0,)
    assert result.specifications[0].value.extensions["acceptance"] == [
        "The declared member check passes."
    ]
    assert result.decisions[0].value.status.value == "accepted"
    assert result.plans[0].value.approved_base == git_output(repository, "rev-parse", "HEAD^")
    assert git_output(repository, "status", "--porcelain") == before


def proposal(repository, migration):
    observed = migration.inventory(repository)
    return migration.parse_proposal(
        {
            "schema_version": 1,
            "source_commit": observed.commit,
            "inventory_digest": observed.digest,
            "topics": [
                {
                    "id": "validation",
                    "version": 1,
                    "summary": "Validation establishes source evidence.",
                }
            ],
            "clauses": [
                {
                    "sources": [{"path": "docs/decisions/AD-1.md", "start_line": 6, "end_line": 6}],
                    "clause": {
                        "id": "VAL-001",
                        "version": 1,
                        "topic": "validation",
                        "scope": ["repository"],
                        "statement": "Keep the first failure failed.",
                        "rationale": "Retain the accepted rule.",
                    },
                    "reason": "Select the exact original sentence as one clause.",
                }
            ],
        }
    )


def test_explicit_mapping_previews_original_text_and_never_creates_approval(repository, migration):
    original = (repository / "docs/decisions/AD-1.md").read_bytes()
    before = git_output(repository, "status", "--porcelain")
    result = migration.preview(repository, proposal(repository, migration))
    assert result.status == "unapproved"
    assert result.clauses[0].excerpts == ("Keep the first failure failed.",)
    assert result.clauses[0].clause.id == "VAL-001"
    assert result.requires_review == ("docs/decisions/AD-1.md",)
    assert (repository / "docs/decisions/AD-1.md").read_bytes() == original
    assert git_output(repository, "status", "--porcelain") == before


@pytest.mark.parametrize("damage", ["unknown", "range", "digest", "duplicate"])
def test_bad_mapping_references_never_change_source(repository, migration, damage):
    value = json.loads(json.dumps(contract_mapping(proposal(repository, migration))))
    if damage == "unknown":
        value["clauses"][0]["sources"][0]["path"] = "docs/decisions/missing.md"
    elif damage == "range":
        value["clauses"][0]["sources"][0]["end_line"] = 999
    elif damage == "digest":
        value["inventory_digest"] = "sha256:" + "0" * 64
    else:
        value["clauses"] *= 2
    before = git_output(repository, "status", "--porcelain")
    with pytest.raises(ValueError):
        migration.preview(repository, migration.parse_proposal(value))
    assert git_output(repository, "status", "--porcelain") == before


@pytest.mark.parametrize("acceptance", ["generic", "reversed_exact"])
def test_multiple_clauses_are_never_paired_to_acceptance_by_position(
    repository, migration, acceptance
):
    review = repository / "changes/example/review.toml"
    review.write_text(
        review.read_text()
        + '\n[[review.clauses]]\nid="REQ-002"\nstatement="Preserve the second requirement."\n'
        'disposition="covered"\nspecification="example/behavior"\n'
    )
    spec = repository / "changes/example/specs/behavior.toml"
    choices = (
        ["Suite case A.", "Suite case B."]
        if acceptance == "generic"
        else ["Preserve the second requirement.", "The member implements the approved behavior."]
    )
    source = (
        spec.read_text()
        .replace('["REQ-001"]', '["REQ-001", "REQ-002"]')
        .replace('["The declared member check passes."]', json.dumps(choices))
    )
    spec.write_text(source)
    plan = repository / "changes/example/plans/behavior.md"
    plan.write_text(plan.read_text().replace("| REQ-001 |", "| REQ-001, REQ-002 |"))
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "retain multi-clause source")
    observed = migration.inventory(repository)
    if acceptance == "generic":
        assert all(item.ambiguous and not item.acceptance_indices for item in observed.requirements)
        assert any(item.code == "unassigned_acceptance" for item in observed.issues)
    else:
        assert [item.acceptance_indices for item in observed.requirements] == [(1,), (0,)]
        assert not any(item.ambiguous for item in observed.requirements)
    assert observed.specifications[0].value.extensions["acceptance"] == choices


@pytest.mark.parametrize("base", ["fixture", "0000000000000000000000000000000000000000"])
def test_unresolved_or_unavailable_legacy_base_is_never_replaced_with_head(
    repository, migration, base
):
    plan = repository / "changes/example/plans/behavior.md"
    old = next(line[6:] for line in plan.read_text().splitlines() if line.startswith("Base: "))
    plan.write_text(plan.read_text().replace("Base: " + old, "Base: " + base))
    git_output(repository, "commit", "-am", "retain unresolved legacy base")
    observed = migration.inventory(repository)
    assert observed.plans[0].value.approved_base == base
    assert any(item.code in {"unresolved_base", "unverified_base"} for item in observed.issues)


@pytest.mark.parametrize(
    "damage", ["malformed", "symlink", "review_identity", "specification_owner"]
)
def test_bad_legacy_authorities_are_reported_without_following_or_repairing_them(
    repository, migration, damage
):
    decision = repository / "docs/decisions/AD-1.md"
    if damage == "malformed":
        (repository / "changes/example/specs/behavior.toml").write_text("invalid TOML")
    elif damage == "symlink":
        secret = repository.parent / "unrelated-private-source"
        secret.write_text("unrelated private value")
        decision.unlink()
        decision.symlink_to(secret)
    elif damage == "review_identity":
        review = repository / "changes/example/review.toml"
        review.write_text(review.read_text().replace('id = "example"', 'id = "foreign"', 1))
    else:
        spec = repository / "changes/example/specs/behavior.toml"
        spec.write_text(spec.read_text().replace('id = "example"', 'id = "foreign"'))
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "retain an invalid legacy authority fixture")
    status = git_output(repository, "status", "--porcelain")
    observed = migration.inventory(repository)
    assert observed.issues
    if damage == "symlink":
        assert (
            next(item for item in observed.documents if item.path.endswith("AD-1.md")).status
            == "invalid"
        )
        assert observed.decisions == ()
    if damage == "specification_owner":
        assert observed.requirements[0].ambiguous
    assert git_output(repository, "status", "--porcelain") == status


@pytest.mark.parametrize("partial", [False, True])
def test_supersession_keeps_unaffected_authority_without_reviving_fully_replaced_rules(
    repository, migration, partial
):
    original = repository / "docs/decisions/AD-1.md"
    original.write_text(original.read_text() + "\nSuperseded by: AD-2.md\n")
    (original.parent / "AD-2.md").write_text(
        "# New rule\nStatus: Accepted\nSupersedes: AD-1.md\n"
        + ("Partially supersedes: AD-1.md\n" if partial else "")
    )
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "retain reciprocal supersession")
    selected = proposal(repository, migration)
    if partial:
        assert migration.preview(repository, selected).status == "unapproved"
    else:
        with pytest.raises(ValueError, match="active rule"):
            migration.preview(repository, selected)


@pytest.mark.parametrize("dirty", [False, True])
def test_changed_authorities_invalidate_a_mapping_before_any_adoption(repository, migration, dirty):
    selected = proposal(repository, migration)
    path = repository / "docs/decisions/AD-1.md"
    path.write_text(path.read_text() + "\nA separately changed source rule.\n")
    if not dirty:
        git_output(
            repository, "commit", "-am", "change the authority after the mapping was drafted"
        )
    before = git_output(repository, "status", "--porcelain")
    with pytest.raises(ValueError):
        migration.preview(repository, selected)
    assert git_output(repository, "status", "--porcelain") == before


def test_code_only_commits_do_not_reinterpret_unchanged_legacy_sources(repository, migration):
    selected = proposal(repository, migration)
    (repository / "implementation.py").write_text("assert True\n")
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "independent implementation")
    result = migration.preview(repository, selected)
    assert result.source_commit == selected.source_commit
    assert result.clauses[0].excerpts == ("Keep the first failure failed.",)


def test_real_mapping_commands_are_read_only_and_work_without_engine_site_packages(
    repository, migration
):
    path = repository / "mapping.json"
    path.write_text(json.dumps(contract_mapping(proposal(repository, migration))))
    root = Path(__file__).parents[2]
    engine = migration.__name__.startswith("signetum.")
    runtime = root / "src" if engine else root / "template/.agents/repo-dev/runtime"
    script = (
        "import importlib,sys; sys.path.insert(0,sys.argv.pop(1)); "
        "module=importlib.import_module(sys.argv.pop(1)); "
        "result=module.main(sys.argv[1:]); assert 'pydantic' not in sys.modules; "
        + ("" if engine else "assert 'signetum' not in sys.modules; ")
        + "raise SystemExit(result)"
    )
    before = git_output(repository, "status", "--porcelain")
    for arguments in (["inventory"], ["preview", "--proposal", str(path)]):
        result = subprocess.run(  # noqa: S603 -- known interpreter and fixture-owned read-only arguments
            [
                sys.executable,
                *([] if engine else ["-I", "-S"]),
                "-c",
                script,
                str(runtime),
                migration.__name__,
                *arguments,
                "--repository",
                str(repository),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["status"] == "preview"
    assert git_output(repository, "status", "--porcelain") == before


@pytest.mark.parametrize("damage", ["topic", "blank", "reversed", "outside", "unaccepted"])
def test_mapping_cannot_invent_context_or_select_unowned_or_empty_source(
    repository, migration, damage
):
    if damage == "unaccepted":
        path = repository / "docs/decisions/AD-1.md"
        path.write_text(path.read_text().replace("Status: Accepted", "Status: Proposed"))
        git_output(repository, "commit", "-am", "retain unaccepted decision")
    value = json.loads(json.dumps(contract_mapping(proposal(repository, migration))))
    if damage == "topic":
        value["topics"] = []
    elif damage == "blank":
        value["clauses"][0]["sources"][0].update(start_line=2, end_line=2)
    elif damage == "reversed":
        value["clauses"][0]["sources"][0].update(start_line=6, end_line=5)
    elif damage == "outside":
        value["clauses"][0]["sources"][0]["path"] = "../outside.md"
    with pytest.raises(ValueError):
        migration.preview(repository, migration.parse_proposal(value))


def test_non_authority_reports_are_not_promoted_to_legacy_decisions(repository, migration):
    (repository / "changes/example/report.md").write_text(
        "An old report, not an execution authority.\n"
    )
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "retain an unrelated report")
    observed = migration.inventory(repository)
    assert len(observed.documents) == 4
    assert len(observed.decisions) == 1


@pytest.mark.parametrize("operation", ["inventory", "preview"])
def test_cli_requires_explicit_mapping_input_only_for_preview(
    repository, migration, capsys, operation
):
    arguments = [operation, "--repository", str(repository)]
    if operation == "inventory":
        arguments.extend(["--proposal", str(repository / "unused.json")])
    assert migration.main(arguments) == 2
    result = capsys.readouterr()
    assert result.out == ""
    assert json.loads(result.err)["status"] == "invalid"


def _declare_working_set(repository, *, declared=True, body=None):
    path = repository / "docs/architecture/constraints.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        body
        or """# Current constraints

Reopen only through an accepted decision quoting the old rule and its reason.

## Validation

| do_not | because |
| --- | --- |
| Clear the first failure with retry | Retry is diagnostic. Reopen when its contract changes. |
"""
    )
    text = MANIFEST
    if declared:
        text += """\n[[migration.sources]]
id = "constraints"
path = "docs/architecture/constraints.md"
format = "markdown-constraints@1"
"""
    (repository / "signetum.toml").write_text(text)
    git_output(repository, "add", ".")
    git_output(repository, "commit", "-m", "declare historical working-set source")
    return path


def test_explicit_working_set_inventory_retains_rows_and_real_source_identity(
    repository, migration
):
    path = _declare_working_set(repository)
    before = path.read_bytes()
    result = migration.inventory(repository)
    source = result.working_sets[0]
    assert source.id == "constraints"
    assert source.path == "docs/architecture/constraints.md"
    assert source.blob == git_output(repository, "rev-parse", "HEAD:" + source.path)
    assert source.status == "declared_working_set"
    assert source.rows[0].do_not == "Clear the first failure with retry"
    assert source.rows[0].because == ("Retry is diagnostic. Reopen when its contract changes.")
    assert source.rows[0].topic == "Validation"
    assert source.rows[0].start_line == source.rows[0].end_line == 9
    assert "accepted decision quoting the old rule" in source.context
    assert len(result.decisions) == 1
    assert path.read_bytes() == before
    assert not git_output(repository, "status", "--porcelain")


def test_undeclared_working_sets_do_not_become_migration_authority(repository, migration):
    _declare_working_set(repository, declared=False)
    result = migration.inventory(repository)
    assert result.working_sets == ()
    assert {item.path for item in result.documents} == {
        "changes/example/review.toml",
        "changes/example/specs/behavior.toml",
        "changes/example/plans/behavior.md",
        "docs/decisions/AD-1.md",
    }


def _working_set_proposal(repository, migration):
    result = migration.inventory(repository)
    row = result.working_sets[0].rows[0]
    return migration.parse_proposal(
        dict(
            schema_version=1,
            source_commit=result.commit,
            inventory_digest=result.digest,
            topics=[dict(id="validation", version=1, summary="Validation constraints.")],
            clauses=[
                dict(
                    sources=[
                        dict(
                            path=result.working_sets[0].path,
                            start_line=row.start_line,
                            end_line=row.end_line,
                        )
                    ],
                    clause=dict(
                        id="VAL-1",
                        version=1,
                        topic="validation",
                        scope=["repository"],
                        statement=row.do_not,
                        rationale=row.because,
                    ),
                    reason="Preserve the exact existing rule, rationale and reopen condition.",
                )
            ],
        )
    )


def test_working_set_mapping_keeps_original_text_and_never_grants_acceptance(repository, migration):
    path = _declare_working_set(repository)
    before = path.read_bytes()
    result = migration.preview(repository, _working_set_proposal(repository, migration))
    assert result.status == "unapproved"
    assert result.clauses[0].excerpts == (path.read_text().splitlines()[8],)
    assert "docs/architecture/constraints.md" in result.requires_review
    assert "docs/decisions/AD-1.md" in result.unmapped
    assert path.read_bytes() == before
    assert not (repository / "changes/example/events.jsonl").exists()


@pytest.mark.parametrize("damage", ["dirty", "missing", "symlink", "escape", "format"])
def test_invalid_working_set_source_declarations_refuse_without_following_them(
    repository, migration, damage
):
    path = _declare_working_set(repository)
    if damage == "dirty":
        path.write_text(path.read_text() + "Uncommitted rule.\n")
    elif damage == "missing":
        path.unlink()
        git_output(repository, "commit", "-am", "remove declared working set")
    elif damage == "symlink":
        path.unlink()
        path.symlink_to(repository / "seed")
        git_output(repository, "add", ".")
        git_output(repository, "commit", "-m", "replace working set by a symlink")
    else:
        manifest = repository / "signetum.toml"
        text = manifest.read_text().replace(
            "docs/architecture/constraints.md" if damage == "escape" else "markdown-constraints@1",
            "../outside.md" if damage == "escape" else "invented@99",
        )
        manifest.write_text(text)
        git_output(repository, "commit", "-am", "declare an invalid source binding")
    before = git_output(repository, "status", "--porcelain")
    with pytest.raises(ValueError):
        migration.inventory(repository)
    assert git_output(repository, "status", "--porcelain") == before


def test_incomplete_constraint_rows_remain_explicit_review_issues(repository, migration):
    _declare_working_set(
        repository,
        body="""# Constraints
| do_not | because |
| --- | --- |
| Valid prohibition | Its original basis. |
| Missing basis | |
""",
    )
    result = migration.inventory(repository)
    assert len(result.working_sets[0].rows) == 1
    assert any(issue.code == "ambiguous_working_set_row" for issue in result.issues)


def test_working_set_edits_invalidate_existing_mapping(repository, migration):
    path = _declare_working_set(repository)
    candidate = _working_set_proposal(repository, migration)
    path.write_text(path.read_text().replace("Retry is diagnostic.", "A revised basis."))
    git_output(repository, "commit", "-am", "revise working-set authority")
    with pytest.raises(ValueError, match="inventory changed"):
        migration.preview(repository, candidate)


def test_partial_working_set_mapping_reports_the_remaining_exact_rows(repository, migration):
    _declare_working_set(
        repository,
        body="""# Constraints
| do_not | because |
| --- | --- |
| First prohibition | Its original basis. |
| Second prohibition | Its other basis. Reopen when approved. |
""",
    )
    result = migration.preview(repository, _working_set_proposal(repository, migration))
    assert [(span.path, span.start_line, span.end_line) for span in result.unmapped_rows] == [
        ("docs/architecture/constraints.md", 5, 5)
    ]
    assert result.status == "unapproved"


@pytest.mark.parametrize("field", ["statement", "rationale"])
def test_working_set_mapping_cannot_drop_the_original_rule_or_its_reopen_condition(
    repository, migration, field
):
    _declare_working_set(repository)
    candidate = _working_set_proposal(repository, migration)
    mapped = candidate.clauses[0]
    revised = replace(mapped.clause, **{field: "A weaker replacement."})
    candidate = replace(candidate, clauses=(replace(mapped, clause=revised),))
    with pytest.raises(ValueError, match="must preserve"):
        migration.preview(repository, candidate)


def test_fenced_tables_are_context_not_inferred_working_set_rules(repository, migration):
    _declare_working_set(
        repository,
        body="""# Constraints
An example follows, not a rule.
```markdown
| do_not | because |
| --- | --- |
| Invented rule | Only an example. |
```
""",
    )
    result = migration.inventory(repository)
    assert result.working_sets[0].rows == ()
    assert any(item.code == "unmapped_working_set" for item in result.issues)


def test_working_set_inventory_runs_through_the_isolated_public_frontend(repository, migration):
    _declare_working_set(repository)
    if migration.__name__ == "signetum.migration":
        arguments = ["-m", "signetum.migration"]
    else:
        runtime = str(Path(__file__).parents[2] / "template/.agents/repo-dev/runtime")
        script = (
            "import sys;sys.path.insert(0,sys.argv[1]);"
            "from _signetum_runtime.migration import main;"
            "assert 'signetum' not in sys.modules and 'pydantic' not in sys.modules;"
            "raise SystemExit(main(sys.argv[2:]))"
        )
        arguments = ["-I", "-S", "-c", script, runtime]
    completed = subprocess.run(  # noqa: S603 -- declared interpreter and disposable source fixture
        [sys.executable, *arguments, "inventory", "--repository", str(repository)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)["result"]
    assert result["schema_version"] == 2
    assert result["working_sets"][0]["status"] == "declared_working_set"
    assert not git_output(repository, "status", "--porcelain")
