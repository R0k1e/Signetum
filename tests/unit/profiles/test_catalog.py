"""Installed and generated catalog parsing retain one portable contract."""

import json
import tomllib
from dataclasses import asdict
from pathlib import Path

import pytest
from signetum.profiles.catalog import (
    PROFILE_RESOURCE_NAMES,
    ProfileError,
    load_catalog,
    resolve_profiles,
)

ROOT = Path(__file__).parents[3]


@pytest.fixture
def documents():
    return {
        name: (
            ROOT / "skills/signetum/scripts/engine/signetum/resources/profiles" / name
        ).read_text()
        for name in PROFILE_RESOURCE_NAMES
    }


@pytest.fixture
def resolve():
    def installed(documents, selected):
        catalog = load_catalog(documents.__getitem__)
        return [asdict(item) for item in resolve_profiles(tuple(selected), catalog=catalog)]

    return installed


def test_catalog_uses_owned_defaults_and_retains_graph_metadata(resolve, documents):
    profiles = resolve(documents, ["python-default@1", "git-worktrunk@1"])
    assert [item["identity"] for item in profiles] == [
        "shared-core@1",
        "python-default@1",
        "git-worktrunk@1",
    ]
    assert list(profiles[0]["tools"]) == []
    expected = tomllib.loads(documents["python-default-v1.toml"])["shards"]
    assert json.loads(json.dumps(profiles[1]["shards"])) == expected


@pytest.mark.parametrize(
    "damage",
    [
        "schema",
        "boolean-schema",
        "missing",
        "extra",
        "authorities",
        "requires",
        "tools",
        "duplicate",
        "cycle",
        "dependency",
        "authority",
    ],
)
def test_bad_catalogs_are_refused_by_both_distributed_consumers(resolve, documents, damage):
    name = "git-worktrunk-v1.toml"
    source = documents[name]
    if damage == "schema":
        source = source.replace("schema_version = 1", "schema_version = 2")
    elif damage == "boolean-schema":
        source = source.replace("schema_version = 1", "schema_version = true")
    elif damage == "missing":
        source = source.replace('identity = "git-worktrunk@1"\n', "")
    elif damage == "extra":
        source += '\nunrecognized = "value"\n'
    elif damage == "authorities":
        source = source.replace(
            'authorities = ["workspace-isolation"]', 'authorities = "workspace-isolation"'
        )
    elif damage == "requires":
        source = source.replace('requires = ["shared-core@1"]', 'requires = "shared-core@1"')
    elif damage == "tools":
        source += "\ntools = 17\n"
    elif damage == "duplicate":
        source = source.replace('identity = "git-worktrunk@1"', 'identity = "shared-core@1"')
    elif damage == "cycle":
        documents["shared-core-v1.toml"] = documents["shared-core-v1.toml"].replace(
            "requires = []", 'requires = ["git-worktrunk@1"]'
        )
    elif damage == "dependency":
        source = source.replace('requires = ["shared-core@1"]', 'requires = ["missing@1"]')
    else:
        source = source.replace(
            'authorities = ["workspace-isolation"]', 'authorities = ["python-quality"]'
        )
    documents[name] = source
    with pytest.raises(ProfileError):
        resolve(documents, ["python-default@1", "git-worktrunk@1"])
