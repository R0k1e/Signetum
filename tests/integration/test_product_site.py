from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from typer.testing import CliRunner

from signetum.cli import app
from signetum.site import build_site

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = "https://r0k1e.github.io/Signetum/"


class HomeLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.targets: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a" and "home" in (attributes.get("rel") or "").split():
            self.targets.append(attributes.get("href"))


def test_site_build_emits_an_exact_public_artifact(tmp_path: Path) -> None:
    destination = tmp_path / "public"

    files = build_site(ROOT, destination)

    assert set(files) == {
        "assets/signetum-mark.svg",
        "assets/signetum-social-preview.png",
        "fonts/InstrumentSerif-Regular.ttf",
        "fonts/OFL.txt",
        "index.html",
        "install.js",
        "robots.txt",
        "sitemap.xml",
        "styles.css",
        "zh-CN/index.html",
    }
    assert {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    } == set(files)
    for source, output in (
        ("assets/brand/signetum-mark.svg", "assets/signetum-mark.svg"),
        ("assets/brand/signetum-social-preview.png", "assets/signetum-social-preview.png"),
        ("site/fonts/InstrumentSerif-Regular.ttf", "fonts/InstrumentSerif-Regular.ttf"),
        ("site/fonts/OFL.txt", "fonts/OFL.txt"),
        ("site/install.js", "install.js"),
    ):
        assert (
            hashlib.sha256((destination / output).read_bytes()).digest()
            == hashlib.sha256((ROOT / source).read_bytes()).digest()
        )


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

    home_links = HomeLinks()
    home_links.feed(html)
    assert home_links.targets == ["./"]
    assert f'<html lang="{language}">' in html
    assert f'<link rel="canonical" href="{canonical}">' in html
    assert f'hreflang="{language}"' in html
    assert f'href="{alternate}"' in html
    assert 'property="og:image"' in html
    assert 'name="twitter:card" content="summary_large_image"' in html
    assert '"@type": "SoftwareApplication"' in html
    assert "https://github.com/r0k1e/Signetum" in html
    assert re.search(r"<title>[^<]+</title>", html)
    assert re.search(r'name="description" content="[^\"]+"', html)


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
    assert payload["files"] == 10


def test_template_has_no_product_site_or_brand_payload() -> None:
    forbidden = {"site", "assets"}
    assert forbidden.isdisjoint(
        path.name for path in (ROOT / "tests/fixtures/portable-python").iterdir()
    )
    assert not (ROOT / "tests/fixtures/portable-python/.github/workflows/pages.yml").exists()
