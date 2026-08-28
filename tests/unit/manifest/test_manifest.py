from pathlib import Path

import pytest

from development_foundation.manifest import ManifestError, load_manifest

FIXTURE = Path(__file__).parents[2] / "fixtures" / "repository.yaml"


def test_load_manifest_preserves_downstream_repository_facts() -> None:
    manifest = load_manifest(FIXTURE)

    assert manifest.schema_version == 1
    assert manifest.foundation.version == "2.0.0"
    assert manifest.repository.architecture == "docs/ARCHITECTURE.md"
    assert manifest.profiles == (
        "python-uv@1",
        "git-worktrunk@1",
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("schema_version: 2\n", "unsupported manifest schema: 2"),
        (
            """schema_version: 1
foundation:
  version: main
  digest: sha256:aa
profiles: []
repository: {}
""",
            "foundation.version must be an immutable semantic version",
        ),
        (
            """schema_version: 1
foundation:
  version: 2.0.0
  digest: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
profiles: []
repository:
  architecture: /tmp/architecture.md
  specifications: changes
  plans: changes
  decisions: docs/decisions
  validation: tools/validate.py
  delivery_state: .foundation/delivery
""",
            "repository.architecture must be repository-relative",
        ),
        (
            """schema_version: 1
foundation:
  version: 2.0.0
  digest: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
profiles: [python-uv@1, python-uv@1]
repository:
  architecture: docs/ARCHITECTURE.md
  specifications: changes
  plans: changes
  decisions: docs/decisions
  validation: tools/validate.py
  delivery_state: .foundation/delivery
""",
            "profiles must contain unique identities",
        ),
    ],
)
def test_invalid_manifest_is_rejected(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "repository.yaml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ManifestError, match=message):
        load_manifest(path)
