"""Real Git members may inherit tests only across non-selecting fixups."""

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from change_fixtures import commit_approval
from pydantic import JsonValue
from signetum import lifecycle
from signetum.evidence.receipts import EvidenceReceipt
from signetum.git import git_output
from signetum.validation.receipt_store import ReceiptStore
from test_workspace_operations import commit_file, opened


@pytest.fixture
def runtime():
    return lifecycle


def configured(repository, runtime):
    root, state = repository
    manifest = root / "signetum.toml"

    def command(name):
        return json.dumps(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; import sys; p=Path(sys.argv[1]); "
                "p.write_text(p.read_text()+'x' if p.exists() else 'x')",
                str(state / name),
            ]
        )

    original = manifest.read_text().replace(
        "[signetum]",
        '[signetum]\nevidence_protocol = "reposeal.validation-evidence@3"\n'
        + 'evidence_schema_digest = "sha256:'
        + "0" * 64
        + '"\n',
    )
    text = original.replace('paths = ["**"]', 'paths = ["src/**"]')
    text = text.replace(
        'decisions = "docs/decisions"', 'decisions = "docs/decisions"\nlockfiles = ["fixture.lock"]'
    )
    (root / "fixture.lock").write_text("locked-v1")
    text = text.replace(
        'member_required = ["test:check"]', 'member_required = ["test:check", "test:static"]'
    )
    text = text.replace(
        'name = "test:check"\ncommand = ["true"]',
        'name = "test:check"\ninherit = true\ncommand = ' + command("tests"),
    )
    text += (
        '\n[[impact.rules]]\nname = "docs"\npaths = ["docs/**", "changes/**"]\n'
        'shards = ["test:static"]\n'
    )
    text += '\n[[validation.shards]]\nname = "test:static"\ncommand = ' + command("static") + "\n"
    text += (
        '\n[[validation.tools]]\nname = "fixture"\nidentity_command = '
        + json.dumps(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text())",
                str(state / "tool"),
            ]
        )
        + "\n"
    )
    (root / "selector.py").write_text("""import json,sys
q=json.load(sys.stdin)
coverage=[]
for p in q["files"]:
    known=p.startswith(("src/","docs/","changes/"))
    coverage.append(dict(path=p,status="covered" if known else "unexplained",
                         shards=["test:check"] if p.startswith("src/") else [],
                         reason="Explicit fixture selection."))
print(json.dumps(dict(protocol="signetum.selection@1",request_digest=q["request_digest"],
                     coverage=coverage,targets=[])))
""")
    text += '\n[impact.provider]\nprotocol="signetum.selection@1"\nentrypoint="selector.py"\n'
    text += "command=" + json.dumps([sys.executable, "{selector}"]) + "\n"
    text += (
        'tools=[{name="selector-python",identity_command='
        + json.dumps([sys.executable, "--version"])
        + "}]\n"
    )
    manifest.write_text(text)
    (state / "tool").write_text("v1")
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "declare test inheritance boundary")
    member = opened(root, "plan/inheritance")
    commit_approval(member, "example")
    (member / "src").mkdir()
    commit_file(member, "src/feature.py", "pass\n")
    first = runtime.validate(member, "member")
    return member, state, first


def test_documentation_fixup_inherits_tests_but_reruns_static(repository, runtime):
    member, state, first = configured(repository, runtime)
    (member / "docs").mkdir()
    tip = commit_file(member, "docs/note.md")
    current = runtime.validate(member, "member")
    assert current["source"] == tip != first["source"]
    assert (state / "tests").read_text() == "x"
    assert (state / "static").read_text() == "xx"
    evidence = current["evidence"]
    assert isinstance(evidence, dict)
    inherited = evidence["extensions"]["inherited_test_evidence_from"]
    assert inherited["commit"] == first["source"]


def test_a_selecting_path_modified_then_reverted_still_forces_fresh_tests(repository, runtime):
    member, state, _ = configured(repository, runtime)
    original = (member / "src/feature.py").read_text()
    commit_file(member, "src/feature.py", "intervening = True\n")
    commit_file(member, "src/feature.py", original)
    (member / "docs").mkdir()
    commit_file(member, "docs/note.md")
    current = runtime.validate(member, "member")
    assert (state / "tests").read_text() == "xx"
    evidence = current["evidence"]
    assert isinstance(evidence, dict)
    assert "inherited_test_evidence_from" not in evidence["extensions"]


def test_final_executes_test_shards_even_with_ancestor_member_evidence(repository, runtime):
    root, _ = repository
    member, state, _ = configured(repository, runtime)
    batch = Path(str(lifecycle.batch_open(root, (member,))["worktree"]))
    before = (state / "tests").read_text()
    final = runtime.validate(batch, "final")
    assert (state / "tests").read_text() == before + "x"
    evidence = final["evidence"]
    assert isinstance(evidence, dict)
    assert "inherited_test_evidence_from" not in evidence["extensions"]


@pytest.mark.parametrize(
    "change",
    ["source", "tool", "unknown", "manifest", "lockfile", "invalid-receipt", "different-base"],
)
def test_incompatible_fixup_or_nearest_evidence_runs_tests(repository, change, runtime):
    member, state, first = configured(repository, runtime)
    if change == "source":
        commit_file(member, "src/feature.py", "value = 1\n")
    elif change == "unknown":
        commit_file(member, "unknown.txt")
    elif change == "lockfile":
        commit_file(member, "fixture.lock", "locked-v2")
    else:
        (member / "docs").mkdir()
        commit_file(member, "docs/note.md")
        if change == "tool":
            (state / "tool").write_text("v2")
        elif change == "manifest":
            commit_file(
                member, "signetum.toml", (member / "signetum.toml").read_text() + "\n# changed\n"
            )
        else:
            receipt = Path(first["receipt"])
            raw_path = receipt.with_name(receipt.name.replace("-lifecycle-", "-"))
            raw = json.loads(raw_path.read_text())
            raw["identity"]["base" if change == "different-base" else "tree"] = "f" * 40
            raw_path.write_text(json.dumps(raw))
    current = runtime.validate(member, "member")
    assert (state / "tests").read_text() == "xx"
    evidence = current["evidence"]
    assert isinstance(evidence, dict)
    assert "inherited_test_evidence_from" not in evidence["extensions"]


@pytest.mark.parametrize("damage", ["invalid", "malformed", "unlocatable"])
def test_incompatible_nearest_receipt_does_not_fall_back_to_older_evidence(
    repository, damage, runtime
):
    member, state, _ = configured(repository, runtime)
    (member / "docs").mkdir()
    commit_file(member, "docs/one.md")
    nearest = runtime.validate(member, "member")
    path = nearest["receipt"]
    assert isinstance(path, str)
    lifecycle_path = Path(path)
    raw_path = lifecycle_path.with_name(lifecycle_path.name.replace("-lifecycle-", "-"))
    raw = json.loads(raw_path.read_text())
    raw["valid"] = False
    raw_path.write_text("{" if damage in {"malformed", "unlocatable"} else json.dumps(raw))
    if damage == "unlocatable":
        lifecycle_path.write_text("{")
    commit_file(member, "docs/two.md")
    runtime.validate(member, "member")
    assert (state / "tests").read_text() == "xx"


def test_an_ancestor_with_recovered_failure_requires_fresh_normal_tests(repository, runtime):
    member, state, first = configured(repository, runtime)
    evidence = first["evidence"]
    assert isinstance(evidence, dict)
    historical = EvidenceReceipt.from_json(json.dumps(evidence))
    defect: dict[str, JsonValue] = {
        "shard": "test:check",
        "node_id": "test_contract",
        "first_failure": [{"phase": "call", "outcome": "failed", "diagnostic": "retained failure"}],
    }
    ReceiptStore(runtime._receipt_root(member)).write(
        "member", replace(historical, extensions={"recovered_flake_defects": [defect]})
    )
    (member / "docs").mkdir()
    commit_file(member, "docs/one.md")
    ready = runtime.validate(member, "member")
    assert (state / "tests").read_text() == "xx"
    assert isinstance(ready["evidence"], dict)
    assert "inherited_test_evidence_from" not in ready["evidence"].get("extensions", {})
    commit_file(member, "docs/two.md")
    runtime.validate(member, "member")
    assert (state / "tests").read_text() == "xx"
