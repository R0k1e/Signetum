from importlib.resources import files

from reposeal.resources import profiles, schemas


def test_schema_and_profile_resources_are_packaged() -> None:
    assert (files(schemas) / "repository-manifest-v1.schema.json").is_file()
    assert (files(schemas) / "validation-graph-v2.schema.json").is_file()
    assert (files(schemas) / "validation-receipt-v2.schema.json").is_file()
    assert (files(profiles) / "python-uv-v1.yaml").is_file()
    assert (files(profiles) / "git-worktrunk-v1.yaml").is_file()
