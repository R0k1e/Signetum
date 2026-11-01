"""Manifest defaults, rejection and validation identity agree across frontends."""

import re
from pathlib import Path

import pytest
from signetum.manifest import ManifestError, load_manifest
from signetum.validation.repository import configured_validation

ROOT = Path(__file__).parents[2]


def replace(text, original, candidate):
    assert original in text
    return text.replace(original, candidate, 1)


@pytest.fixture
def manifest_file(tmp_path):
    path = tmp_path / "signetum.toml"
    path.write_text((ROOT / "tests/fixtures/portable-python/signetum.toml").read_text())
    return path


def test_native_configuration_projection_binds_identical_declared_inputs(manifest_file):
    installed_graph, installed = configured_validation(load_manifest(manifest_file))
    assert installed_graph.gate("member").shards
    assert installed.schema_digest == load_manifest(manifest_file).signetum.evidence_schema_digest


def test_native_loader_supplies_the_same_declared_defaults(manifest_file):
    text = re.sub(
        r"^evidence_(?:protocol|schema_digest) = .*\n",
        "",
        manifest_file.read_text(),
        flags=re.MULTILINE,
    )
    manifest_file.write_text(text)
    installed = load_manifest(manifest_file)
    assert installed.signetum.evidence_protocol == "reposeal.validation-evidence@3"
    assert installed.signetum.evidence_schema_digest.startswith("sha256:")
    assert installed.validation.shards[0].timeout_seconds > 0
    assert installed.validation.shards[0].inherit is False


@pytest.mark.parametrize(
    "damage",
    [
        "root-extra",
        "protocol-type",
        "retired-field",
        "repository-extra",
        "change-root",
        "escape",
        "impact-name",
        "impact-paths",
        "retired-recovery",
        "shard-extra",
        "command-empty",
        "inherit-type",
        "workers-type",
        "timeout",
        "missing-member",
        "identity-empty",
    ],
)
def test_native_loaders_reject_the_same_invalid_contract(manifest_file, damage):
    text = manifest_file.read_text()
    substitutions = {
        "root-extra": ("schema_version = 5\n", "schema_version = 5\nunexpected = true\n"),
        "protocol-type": ("protocol = 2", 'protocol = "2"'),
        "retired-field": ("[signetum]\n", '[signetum]\ntemplate_version = "main"\n'),
        "repository-extra": ("[repository]\n", "[repository]\nunexpected = true\n"),
        "change-root": ('changes = "changes"', 'changes = "changes/*"'),
        "escape": ('architecture = "docs/ARCHITECTURE.md"', 'architecture = "../outside.md"'),
        "impact-name": ('name = "python.source"', 'name = "Invalid"'),
        "impact-paths": ('paths = ["src/**"]', 'paths = "src/**"'),
        "retired-recovery": ("[validation]\n", "[validation]\nrecovery_window = 20\n"),
        "shard-extra": ('name = "python:sync"\n', 'name = "python:sync"\nunexpected = true\n'),
        "command-empty": ('command = ["uv", "sync", "--locked"]', "command = []"),
        "inherit-type": ('name = "python:sync"\n', 'name = "python:sync"\ninherit = "false"\n'),
        "workers-type": ('name = "python:sync"\n', 'name = "python:sync"\nworkers = true\n'),
        "timeout": ('name = "python:sync"\n', 'name = "python:sync"\ntimeout_seconds = 0\n'),
        "missing-member": ('name = "member"\n', 'name = "other"\n'),
        "identity-empty": ('identity_command = ["uv", "--version"]', 'identity_command = [""]'),
    }
    manifest_file.write_text(replace(text, *substitutions[damage]))
    with pytest.raises(ManifestError):
        load_manifest(manifest_file)
