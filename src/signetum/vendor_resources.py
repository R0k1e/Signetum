"""Redistribute the locked upstream YAML reader without maintaining a parser fork."""

import argparse
import json
import re
import tomllib
from importlib.metadata import distribution
from importlib.resources import files
from pathlib import Path

RESOURCE_DIRECTORY = "vendor_yaml"


def upstream_yaml_payload() -> dict[str, bytes]:
    """Read exact pure-Python upstream files and their distribution license."""
    package = distribution("PyYAML")
    root = files("yaml")
    names = sorted(
        path.name
        for path in root.iterdir()
        if path.name.endswith(".py") and path.name != "cyaml.py"
    )
    licenses = [entry for entry in package.files or () if entry.name == "LICENSE"]
    if len(licenses) != 1:
        raise ValueError("PyYAML must declare exactly one distribution license")
    provenance = (
        'distribution = "PyYAML"\n'
        + "version = "
        + json.dumps(package.version)
        + "\n"
        + "module_files = "
        + json.dumps(names)
        + "\n"
        + "native_extensions = false\n"
    ).encode()
    return {
        **{name: (root / name).read_bytes() for name in names},
        "LICENSE": Path(str(package.locate_file(licenses[0]))).read_bytes(),
        "PROVENANCE.toml": provenance,
    }


def yaml_payload() -> dict[str, bytes]:
    """Read packaged bytes; installed generation requires no YAML dependency."""
    root = files("signetum.resources") / RESOURCE_DIRECTORY
    provenance = (root / "PROVENANCE.toml").read_bytes()
    metadata = tomllib.loads(provenance.decode("utf-8"))
    names = metadata.get("module_files")
    if (
        metadata.get("distribution") != "PyYAML"
        or not isinstance(metadata.get("version"), str)
        or metadata.get("native_extensions") is not False
        or not isinstance(names, list)
        or any(
            not isinstance(name, str) or re.fullmatch(r"[a-z_]+\.py", name) is None
            for name in names
        )
        or names != sorted(set(names))
        or "__init__.py" not in names
        or "cyaml.py" in names
    ):
        raise ValueError("invalid packaged YAML provenance")
    expected = {name + ".txt" for name in names} | {"LICENSE", "PROVENANCE.toml"}
    if {path.name for path in root.iterdir()} != expected:
        raise ValueError("packaged YAML inventory differs from its provenance")
    return {
        **{name: (root / (name + ".txt")).read_bytes() for name in names},
        "LICENSE": (root / "LICENSE").read_bytes(),
        "PROVENANCE.toml": provenance,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    arguments = parser.parse_args()
    payload = upstream_yaml_payload()
    arguments.directory.mkdir(parents=True, exist_ok=True)
    for name, content in payload.items():
        target = arguments.directory / (name + ".txt" if name.endswith(".py") else name)
        target.write_bytes(content)


if __name__ == "__main__":
    main()
