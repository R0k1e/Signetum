"""Generated template runtime binds the installed engine source bytes."""

import ast
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from importlib.resources import files
from pathlib import Path

import pytest
from fixture_rendering import render_template, validate_template

from signetum.profiles.catalog import PROFILE_RESOURCE_NAMES
from signetum.runtime_generation import (
    RUNTIME_DIRECTORY,
    generate_runtime,
    portable_source,
    runtime_files,
    runtime_problems,
)
from signetum.vendor_resources import upstream_yaml_payload, yaml_payload

ROOT = Path(__file__).parents[2]


def test_generation_is_deterministic_and_refuses_drift(tmp_path):
    first = runtime_files()
    assert runtime_files() == first
    generate_runtime(tmp_path)
    target = tmp_path / ".agents/signetum/runtime/_signetum_runtime/git.py"
    target.write_bytes(target.read_bytes() + b"\n# hand edit\n")
    with pytest.raises(ValueError, match="generated runtime"):
        generate_runtime(tmp_path, check=True)
    generate_runtime(tmp_path)
    generate_runtime(tmp_path, check=True)


def test_template_validation_refuses_a_stale_shared_runtime(tmp_path):
    source = tmp_path / "fixture"
    shutil.copytree(ROOT / "tests/fixtures/portable-python", source)
    target = source / ".agents/signetum/runtime/_signetum_runtime/findings.py"
    target.write_bytes(target.read_bytes() + b"\n# stale implementation\n")
    assert any("generated runtime" in problem for problem in validate_template(source).problems)
    with pytest.raises(ValueError, match="generated runtime"):
        render_template(source, tmp_path / "rendered")


def test_interpreter_caches_do_not_enter_rendered_artifacts(tmp_path):
    source = tmp_path / "fixture"
    shutil.copytree(ROOT / "tests/fixtures/portable-python", source)
    shutil.rmtree(source / RUNTIME_DIRECTORY)
    assert validate_template(source).valid
    cache = source / ".agents/stale-host/__pycache__"
    cache.mkdir(parents=True)
    (cache / "host.pyc").write_bytes(b"host-specific bytecode")
    target = tmp_path / "rendered"
    report = render_template(source, target)
    assert not any("__pycache__" in path or path.endswith(".pyc") for path in report.files)
    assert not list(target.rglob("*.pyc"))
    assert not (target / ".agents/stale-host").exists()
    assert not (source / RUNTIME_DIRECTORY).exists()
    assert runtime_problems(target) == ()


@pytest.mark.parametrize(
    "source", ["import pydantic\n", "from signetum.release import build_release_metadata\n"]
)
def test_portable_source_rejects_unbundled_dependencies(source):
    with pytest.raises(ValueError, match="dependency"):
        portable_source("signetum.git", source)


def test_flattened_import_order_preserves_implementation_statements():
    source = (
        "from signetum.validation import ValidationGraph\n"
        "from signetum.validation.execution import ValidationInputs\n\n"
        "def preserved(value):\n    return {'value': value, 'paths': ['a', 'b']}\n"
    )
    generated = ast.parse(portable_source("signetum.validation.inheritance", source))
    assert [node.module for node in generated.body if isinstance(node, ast.ImportFrom)] == [
        "execution",
        "validation",
    ]
    assert ast.dump(generated.body[-1]) == ast.dump(ast.parse(source).body[-1])


@pytest.mark.parametrize("polluted", [False, True])
def test_generated_package_executes_without_engine_or_site_packages(tmp_path, polluted):
    generate_runtime(tmp_path)
    runtime = tmp_path / ".agents/signetum/runtime"
    script = (
        "import sys,json; from pathlib import Path; "
        "sys.path.insert(0,sys.argv[1]); "
        "from _signetum_runtime.git import git_output; "
        "from _signetum_runtime.pip_audit import translate; "
        "print(json.dumps([git_output(Path(sys.argv[2]),'rev-parse','--show-toplevel'),"
        "json.loads(translate('[]'))])); "
        "assert 'signetum' not in sys.modules"
    )
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and isolated fixture argv
        [sys.executable, "-I", "-S", "-c", script, str(runtime), str(ROOT)],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, GIT_DIR=str(tmp_path / "not-the-repository")) if polluted else None,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[1] == {"schema_version": 1, "findings": []}


def test_metadata_verifies_raw_sources_and_generated_outputs():
    outputs = runtime_files()
    metadata = tomllib.loads(outputs["runtime.toml"].decode())
    for module, digest in metadata["sources"].items():
        path = importlib.import_module(module).__file__
        assert path is not None
        assert digest == "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
    for name, digest in metadata["files"].items():
        assert digest == "sha256:" + hashlib.sha256(outputs[name]).hexdigest()


def test_generation_preserves_unmanaged_extensions(tmp_path):
    generate_runtime(tmp_path)
    extra = tmp_path / ".agents/signetum/runtime/_signetum_runtime/local_extension.py"
    extra.write_text("local extension")
    with pytest.raises(ValueError, match="unmanaged"):
        generate_runtime(tmp_path)
    assert extra.read_text() == "local extension"


def test_generation_refuses_a_symlinked_parent(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "fixture"
    target.mkdir()
    (target / ".agents").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        generate_runtime(target)
    assert list(outside.iterdir()) == []


def test_runtime_catalog_resources_are_exact_installed_resource_bytes():
    outputs = runtime_files()
    resources = files("signetum.resources.profiles")
    for name in PROFILE_RESOURCE_NAMES:
        assert outputs["profile_resources/" + name] == (resources / name).read_bytes()


def test_yaml_payload_is_exact_locked_upstream_source_and_license():
    packaged = yaml_payload()
    assert packaged == upstream_yaml_payload()
    assert "cyaml.py" not in packaged
    assert b"Copyright" in packaged["LICENSE"]
    outputs = runtime_files()
    for name, content in packaged.items():
        assert outputs["vendor_yaml/" + name] == content
