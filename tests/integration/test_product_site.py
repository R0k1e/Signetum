from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from reposeal.cli import app
from reposeal.site import build_site

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = "https://r0k1e.github.io/RepoSeal/"


def test_site_build_emits_an_exact_public_artifact(tmp_path: Path) -> None:
    destination = tmp_path / "public"

    files = build_site(ROOT, destination)

    assert set(files) == {
        "assets/reposeal-mark.png",
        "assets/reposeal-social-preview.png",
        "index.html",
        "robots.txt",
        "sitemap.xml",
        "styles.css",
        "zh-CN/index.html",
    }
    assert {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()} == set(files)
    assert hashlib.sha256((destination / "assets/reposeal-mark.png").read_bytes()).digest() == hashlib.sha256(
        (ROOT / "assets/brand/reposeal-mark.png").read_bytes()
    ).digest()


@pytest.mark.parametrize(
    ("page", "language", "canonical", "alternate"),
    (
        ("index.html", "en", CANONICAL, f"{CANONICAL}zh-CN/"),
        ("zh-CN/index.html", "zh-CN", f"{CANONICAL}zh-CN/", CANONICAL),
    ),
)
def test_site_pages_expose_bilingual_discovery_metadata(
    tmp_path: Path, page: str, language: str, canonical: str, alternate: str
) -> None:
    destination = tmp_path / "public"
    build_site(ROOT, destination)
    html = (destination / page).read_text(encoding="utf-8")

    assert f'<html lang="{language}">' in html
    assert f'<link rel="canonical" href="{canonical}">' in html
    assert f'hreflang="{language}"' in html
    assert f'href="{alternate}"' in html
    assert 'property="og:image"' in html
    assert 'name="twitter:card" content="summary_large_image"' in html
    assert '"@type": "SoftwareApplication"' in html
    assert "https://github.com/r0k1e/RepoSeal" in html
    assert "Seal every change with evidence" in html or "让每次变更都有证据" in html


def test_site_build_rejects_an_existing_destination(tmp_path: Path) -> None:
    destination = tmp_path / "public"
    destination.mkdir()

    with pytest.raises(ValueError, match="must not exist"):
        build_site(ROOT, destination)


def test_site_cli_reports_the_built_inventory(tmp_path: Path) -> None:
    destination = tmp_path / "public"

    result = CliRunner().invoke(
        app,
        ["site", "build", "--repository", str(ROOT), "--destination", str(destination)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "built"
    assert payload["files"] == 7


def test_template_has_no_product_site_or_brand_payload() -> None:
    forbidden = {"site", "assets", ".github"}
    assert forbidden.isdisjoint(path.name for path in (ROOT / "template").iterdir())
