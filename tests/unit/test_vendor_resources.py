"""Upstream redistribution preserves bytes and rejects damaged inventories."""

import shutil
import sys
from importlib.resources import files

import pytest

from signetum import vendor_resources


@pytest.mark.parametrize("damage", ["extra", "missing", "provenance"])
def test_packaged_payload_refuses_damaged_resources(tmp_path, monkeypatch, damage):
    root = tmp_path / "vendor_yaml"
    shutil.copytree(str(files("signetum.resources") / "vendor_yaml"), root)
    if damage == "extra":
        (root / "unexpected.py.txt").write_text("unexpected content")
    elif damage == "missing":
        (root / "reader.py.txt").unlink()
    else:
        metadata = root / "PROVENANCE.toml"
        metadata.write_text(
            metadata.read_text().replace("native_extensions = false", "native_extensions = true")
        )
    monkeypatch.setattr(vendor_resources, "files", lambda package: tmp_path)
    with pytest.raises(ValueError, match=r"provenance|inventory"):
        vendor_resources.yaml_payload()


def test_refresh_writes_exact_upstream_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["vendor_resources", str(tmp_path)])
    vendor_resources.main()
    for name, content in vendor_resources.upstream_yaml_payload().items():
        target = tmp_path / (name + ".txt" if name.endswith(".py") else name)
        assert target.read_bytes() == content
