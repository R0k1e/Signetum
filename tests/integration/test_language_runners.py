"""Native existing runners qualify the same consolidated lifecycle without Python app metadata."""

import json
import subprocess
import sys
from pathlib import Path
from shutil import which

import pytest
from change_fixtures import consolidated_approval
from signetum import lifecycle
from signetum import lifecycle as core_lifecycle
from signetum.adoption import AdoptionRequest, apply, plan_digest, preview
from signetum.git import git_output
from signetum.manifest import load_manifest
from signetum.profiles.existing_runner import ExistingRunnerRequest, existing_runner_validation
from signetum.runtime_identity import implementation_digest
from signetum.validation import GateDeclaration, ToolDeclaration

ROOT = Path(__file__).parents[2]


def native_application(root, language):
    if language == "python":
        command = (sys.executable, "-m", "unittest", "test_app.py")
        tools = (ToolDeclaration("application-python", (sys.executable, "--version")),)
        source = root / "app.py"
        good = "def twice(value):\n    return value * 2\n"
        (root / "test_app.py").write_text(
            "import unittest\nfrom app import twice\n"
            "class Behavior(unittest.TestCase):\n"
            "    def test_twice(self): self.assertEqual(twice(2), 4)\n"
        )
        metadata = {}
    elif language == "node":
        npm = which("npm")
        node = which("node")
        assert npm is not None and node is not None, (
            "native Node acceptance requires existing tools"
        )
        command = (npm, "--offline", "test")
        tools = (
            ToolDeclaration("npm", (npm, "--version")),
            ToolDeclaration("node", (node, "--version")),
        )
        source = root / "app.js"
        good = "export function twice(value) { return value * 2; }\n"
        (root / "test").mkdir()
        (root / "test/behavior.test.js").write_text(
            "import test from 'node:test';\nimport assert from 'node:assert/strict';\n"
            "import {twice} from '../app.js';\ntest('twice', () => assert.equal(twice(2), 4));\n"
        )
        package = root / "package.json"
        package.write_text(
            json.dumps(
                {
                    "name": "existing-runner-fixture",
                    "private": True,
                    "type": "module",
                    "scripts": {"test": "node --test test/behavior.test.js"},
                }
            )
        )
        metadata = {"package.json": package.read_bytes()}
    else:
        cargo = which("cargo") or str(Path.home() / ".cargo/bin/cargo")
        rustc = which("rustc") or str(Path(cargo).with_name("rustc"))
        assert Path(cargo).is_file() and Path(rustc).is_file(), (
            "native Rust acceptance requires existing tools"
        )
        command = (cargo, "test", "--offline", "--locked", "--target-dir", "target")
        tools = (
            ToolDeclaration("cargo", (cargo, "--version")),
            ToolDeclaration("rustc", (rustc, "--version")),
        )
        (root / "skills/signetum/scripts/engine").mkdir()
        source = root / "src/lib.rs"
        good = (
            "pub fn twice(value: u32) -> u32 { value * 2 }\n"
            "#[cfg(test)] mod tests { use super::*;\n"
            "#[test] fn behavior() { assert_eq!(twice(2), 4); } }\n"
        )
        manifest = root / "Cargo.toml"
        manifest.write_text(
            '[package]\nname="existing-runner-fixture"\nversion="0.1.0"\nedition="2021"\n'
        )
        source.write_text(good)
        result = subprocess.run(  # noqa: S603 -- local installed Cargo, offline dependency-free fixture
            [cargo, "generate-lockfile", "--offline"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        metadata = {name: (root / name).read_bytes() for name in ("Cargo.toml", "Cargo.lock")}
    source.write_text(good)
    (root / ".gitignore").write_text("__pycache__/\n/target/\n")
    return command, tools, source.relative_to(root), good, metadata


def configure_existing_runner(root, language, command, tools, metadata):
    binding = existing_runner_validation(
        ExistingRunnerRequest(
            language=language,
            command=command,
            tools=tools,
            timeout_seconds=60,
        )
    )
    original = load_manifest(root / "signetum.toml")
    app = binding.validation.shards[0]
    text = (
        'schema_version = 4\n[delivery]\nbranch = "main"\n[signetum]\nprotocol = 2\n'
        "[profiles]\nenabled = "
        + json.dumps([binding.identity])
        + '\n[repository]\narchitecture = "docs/ARCHITECTURE.md"\n'
        'changes = "changes"\n'
        'decisions = "docs/decisions"\nlockfiles = ' + json.dumps(sorted(metadata)) + "\n"
        '\n[[impact.rules]]\nname="application"\npaths=["**"]\nshards='
        + json.dumps([app.name])
        + "\n"
        "\n[validation]\nmember_required=" + json.dumps(binding.validation.member_required) + "\n"
    )
    for tool in tools:
        text += (
            "\n[[validation.tools]]\nname="
            + json.dumps(tool.name)
            + "\nidentity_command="
            + json.dumps(tool.identity_command)
            + "\n"
        )
    for shard in (
        *binding.validation.shards,
        *(item for item in original.validation.shards if item.name == "test:prepare"),
    ):
        text += (
            "\n[[validation.shards]]\nname="
            + json.dumps(shard.name)
            + "\ncommand="
            + json.dumps(shard.command)
            + "\ntimeout_seconds=60\n"
        )
    gates = (
        GateDeclaration("prepare", ("test:prepare",)),
        GateDeclaration("batch", ()),
        *binding.validation.gates,
    )
    for gate in gates:
        text += (
            "\n[[validation.gates]]\nname="
            + json.dumps(gate.name)
            + "\nshards="
            + json.dumps(gate.shards)
            + "\n"
        )
    (root / "signetum.toml").write_text(text)
    return binding


@pytest.mark.world
@pytest.mark.parametrize("language", ["python", "node", "rust"])
@pytest.mark.parametrize("frontend", ["engine"])
def test_native_existing_runner_failure_fresh_success_admission_and_final(
    repository, tmp_path, language, frontend, monkeypatch, capsys
):
    root, _ = repository
    runtime = lifecycle if frontend == "engine" else core_lifecycle
    command, tools, source, good, metadata = native_application(root, language)
    tools = (*tools, ToolDeclaration("protocol-python", (sys.executable, "--version")))
    binding = configure_existing_runner(root, language, command, tools, metadata)
    architecture = root / "docs/ARCHITECTURE.md"
    architecture.parent.mkdir(exist_ok=True)
    architecture.write_text("# Existing application architecture\n")
    request = AdoptionRequest(
        manifest=(root / "signetum.toml")
        .read_text()
        .replace("[signetum]", '[signetum]\nengine_digest = "' + implementation_digest() + '"'),
    )
    plan = preview(root, request)
    assert apply(root, plan, plan_digest(plan))["status"] == "applied"
    git_output(root, "add", ".")
    git_output(root, "commit", "-m", "declare the existing application runner")
    git_output(root, "push", "origin", "main")
    base = git_output(root, "rev-parse", "HEAD")
    opened = runtime.workspace_open(root, f"plan/{language}", base)
    member = Path(str(opened["worktree"]))
    consolidated_approval(member, base)
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "approve the existing-runner outcome")
    broken = good.replace("* 2", "* 3")
    if language == "python":
        broken += "# regression version differs in size from the subsequent fix\n"
    (member / source).write_text(broken)
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "reproduce an application behavior failure")
    capsys.readouterr()
    with monkeypatch.context() as context:
        context.chdir(member)
        assert runtime.main(["ready"]) == 3
    failure = json.loads(capsys.readouterr().out)
    assert failure["status"] == "failed"
    assert failure["exit_code"] == 3
    assert not list(runtime._receipt_root(member).glob("member-*.json"))
    (member / source).write_text(good)
    git_output(member, "add", ".")
    git_output(member, "commit", "-m", "fix the application through the same runner")
    ready = runtime.validate(member, "member")
    assert ready["status"] == "ready"
    evidence = ready["evidence"]
    assert isinstance(evidence, dict)
    assert set(evidence["identity"]["profiles"]) == {"shared-core@1", binding.identity}
    admitted = runtime.batch_open(root, (member,))
    batch = Path(str(admitted["batch"]))
    final = runtime.validate(batch, "final")
    assert final["status"] == "final"
    for name, original in metadata.items():
        assert (batch / name).read_bytes() == original
    if language != "python":
        assert not (batch / "pyproject.toml").exists()
        assert not (batch / "uv.lock").exists()
    assert git_output(root, "rev-parse", "main") == base
