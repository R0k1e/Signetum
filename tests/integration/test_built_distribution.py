import subprocess
import sys
from pathlib import Path
from shutil import which
from zipfile import ZipFile

from signetum.runtime_generation import RUNTIME_DIRECTORY, runtime_files


def test_built_wheel_ships_its_declared_resources_without_build_machine_facts() -> None:
    wheels = tuple(Path("dist").glob("signetum-*.whl"))
    assert len(wheels) == 1

    with ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
        payload = "\n".join(
            wheel.read(name).decode("utf-8", errors="replace")
            for name in names
            if name.endswith((".py", ".toml", ".json"))
        )

    assert "signetum/resources/schemas/signetum-v2.schema.json" in names
    assert "signetum/resources/profiles/python-default-v1.toml" in names
    assert "signetum/resources/schemas/validation-graph-v2.schema.json" in names
    assert "signetum/resources/schemas/validation-evidence-v3.schema.json" in names
    assert "signetum/resources/schemas/contracts/release-metadata.schema.json" in names
    assert "signetum/resources/skills/repo-dev/SKILL.md" in names
    assert "signetum/resources/vectors/validation-evidence-v3.json" in names
    # Absence is the contract here, so each value is bound to the reason it
    # must not appear rather than left as a bare literal nobody can extend.
    unrendered_template_placeholder = "placeholder_name"
    build_machine_home = str(Path.home())

    assert unrendered_template_placeholder not in payload
    assert build_machine_home not in payload


def test_installed_wheel_generates_the_same_portable_runtime(tmp_path):
    wheels = tuple(Path("dist").glob("signetum-*.whl"))
    assert len(wheels) == 1
    uv = which("uv")
    assert uv is not None
    environment = tmp_path / "environment"
    python = environment / "bin/python"
    output = tmp_path / "template"
    probe = (
        "from pathlib import Path; import sys,signetum; from importlib.util import find_spec; "
        "assert Path(signetum.__file__).is_relative_to(Path(sys.prefix)); "
        "assert find_spec('pydantic') is None"
    )
    commands = (
        (uv, "venv", "--python", sys.executable, str(environment)),
        (uv, "pip", "install", "--python", str(python), "--no-deps", str(wheels[0].resolve())),
        (str(python), "-I", "-c", probe),
        (str(python), "-I", "-m", "signetum.runtime_generation", str(output)),
    )
    for command in commands:
        subprocess.run(command, check=True, cwd=tmp_path, capture_output=True, text=True)  # noqa: S603 -- fixed tools and disposable artifact paths
    actual = {
        path.name: path.read_bytes()
        for path in (output / RUNTIME_DIRECTORY).iterdir()
        if path.is_file()
    }
    assert actual == runtime_files()
