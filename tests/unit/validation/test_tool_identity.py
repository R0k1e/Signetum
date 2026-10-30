"""Editable source changes must invalidate tools without binding host paths."""

import json
import shutil

from signetum.validation import tool_identity


def test_identity_tracks_source_bytes_but_not_location_or_bytecode(tmp_path, monkeypatch):
    package = tmp_path / "first/signetum"
    (package / "validation").mkdir(parents=True)
    (package / "validation/tool_identity.py").write_text("# identity implementation\n")
    (package / "application.py").write_text("value = 1\n")
    monkeypatch.setattr(tool_identity, "__file__", str(package / "validation/tool_identity.py"))
    first = json.loads(tool_identity.identity())
    (package / "application.py").touch()
    (package / "__pycache__").mkdir()
    (package / "__pycache__/application.pyc").write_bytes(b"generated")
    assert json.loads(tool_identity.identity()) == first
    moved = tmp_path / "second/signetum"
    shutil.copytree(package, moved)
    monkeypatch.setattr(tool_identity, "__file__", str(moved / "validation/tool_identity.py"))
    assert json.loads(tool_identity.identity()) == first
    (moved / "application.py").write_text("value = 2\n")
    assert json.loads(tool_identity.identity())["implementation"] != first["implementation"]
    assert str(tmp_path) not in tool_identity.identity()
