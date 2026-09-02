from pathlib import Path
from zipfile import ZipFile


def test_built_wheel_ships_its_declared_resources_without_build_machine_facts() -> None:
    wheels = tuple(Path("dist").glob("reposeal-*.whl"))
    assert len(wheels) == 1

    with ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
        payload = "\n".join(
            wheel.read(name).decode("utf-8", errors="replace")
            for name in names
            if name.endswith((".py", ".toml", ".json"))
        )

    assert "reposeal/resources/schemas/reposeal-v2.schema.json" in names
    assert "reposeal/resources/profiles/python-default-v1.toml" in names
    assert "reposeal/resources/schemas/validation-graph-v2.schema.json" in names
    assert "reposeal/resources/schemas/validation-evidence-v3.schema.json" in names
    assert "reposeal/resources/schemas/contracts/release-metadata.schema.json" in names
    assert "reposeal/resources/skills/repo-dev/SKILL.md" in names
    assert "reposeal/resources/vectors/validation-evidence-v3.json" in names
    # Absence is the contract here, so each value is bound to the reason it
    # must not appear rather than left as a bare literal nobody can extend.
    unrendered_template_placeholder = "placeholder_name"
    build_machine_home = str(Path.home())

    assert unrendered_template_placeholder not in payload
    assert build_machine_home not in payload
