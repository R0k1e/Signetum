"""The configured member and final test commands partition tree and world evidence."""

import os
import subprocess
import sys
from pathlib import Path

from signetum.manifest import load_manifest
from signetum.validation.repository import configured_validation

ROOT = Path(__file__).parents[3]


def collected(command):
    result = subprocess.run(  # noqa: S603 -- repository-declared argv, collection only
        [*command, "--collect-only", "--no-cov", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, SIGNETUM_VALIDATION_WORKERS="0"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return {
        line.strip()
        for line in result.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    }


def test_real_declared_test_commands_keep_world_queries_out_of_members():
    graph, _ = configured_validation(load_manifest(ROOT / "signetum.toml"))
    shards = {item.name: item for item in graph.shards}
    tree = shards["engine:pytest"]
    world = shards["engine:world-tests"]
    assert tree.evidence == "tree"
    assert world.evidence == "world" and not world.inherit
    assert world.name not in graph.execution_order("member")
    assert world.name in graph.execution_order("final")
    tree_nodes = collected(tree.command)
    world_nodes = collected(world.command)
    all_nodes = collected((sys.executable, "-m", "pytest"))
    assert tree_nodes.isdisjoint(world_nodes)
    assert tree_nodes | world_nodes == all_nodes
    assert any("test_installed_skill" in node for node in tree_nodes)
    assert any("test_native_existing_runner_failure" in node for node in world_nodes)
