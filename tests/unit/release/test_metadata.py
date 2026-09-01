from pathlib import Path
from subprocess import CompletedProcess

import pytest

from reposeal import release
from reposeal.release import ReleaseError, build_metadata, preflight


def test_release_metadata_binds_package_schema_and_skill_identities() -> None:
    repository = Path(__file__).resolve().parents[3]

    metadata = build_metadata(repository, "source-commit")

    assert metadata.source == "source-commit"
    assert {component.name for component in metadata.components} == {
        "package",
        "schemas",
        "repo-dev",
    }
    assert {component.version for component in metadata.components} == {"3.0.0"}
    assert all(component.digest.startswith("sha256:") for component in metadata.components)


def test_preflight_requires_exact_clean_source_and_final_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = Path(__file__).resolve().parents[3]
    receipt_root = tmp_path / "reposeal" / "validation"
    receipt_root.mkdir()
    (receipt_root / "final-proof.json").write_text(
        '{"source":"abc","valid":true}\n', encoding="utf-8"
    )

    def fake_run(command: tuple[str, ...], **kwargs: object) -> CompletedProcess[str]:
        if command[-2:] == ("rev-parse", "HEAD"):
            output = "abc\n"
        elif command[-2:] == ("status", "--porcelain"):
            output = ""
        else:
            output = str(tmp_path) + "\n"
        return CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr(release, "which", lambda executable: "/usr/bin/git")
    monkeypatch.setattr(release.subprocess, "run", fake_run)

    assert preflight(repository, "abc").source == "abc"
    with pytest.raises(ReleaseError, match="differs"):
        preflight(repository, "other")


def test_preflight_refuses_missing_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(release, "which", lambda executable: None)

    with pytest.raises(ReleaseError, match="unavailable"):
        preflight(tmp_path, "abc")
