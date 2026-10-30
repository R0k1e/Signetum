from importlib.resources import files

from signetum.resources import profiles, schemas


def test_schema_and_profile_resources_are_packaged() -> None:
    assert (files(schemas) / "signetum-v2.schema.json").is_file()
    assert (files(schemas) / "validation-graph-v2.schema.json").is_file()
    assert (files(schemas) / "validation-evidence-v3.schema.json").is_file()
    assert (files(profiles) / "python-default-v1.toml").is_file()
    assert (files(profiles) / "git-worktrunk-v1.toml").is_file()
