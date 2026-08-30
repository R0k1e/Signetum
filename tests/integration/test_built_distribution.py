from pathlib import Path
from zipfile import ZipFile


def test_built_wheel_contains_public_resources_and_no_downstream_product_facts() -> None:
    wheels = tuple(Path("dist").glob("reposeal-*.whl"))
    assert len(wheels) == 1

    with ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
        payload = "\n".join(
            wheel.read(name).decode("utf-8", errors="replace")
            for name in names
            if name.endswith((".py", ".yaml", ".json"))
        )

    assert "reposeal/resources/schemas/repository-manifest-v1.schema.json" in names
    assert "reposeal/resources/schemas/validation-graph-v2.schema.json" in names
    assert "reposeal/resources/schemas/validation-receipt-v2.schema.json" in names
    assert "reposeal/resources/profiles/python-uv-v1.yaml" in names
    assert "reposeal/resources/schemas/contracts/release-metadata.schema.json" in names
    assert "reposeal/resources/skills/repo-dev/SKILL.md" in names
    assert "placeholder_name" not in payload
    assert "PyLM" not in payload
    assert "/Users/" not in payload
