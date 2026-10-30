"""Build the engine-owned static product site as an exact artifact."""

from __future__ import annotations

import shutil
from pathlib import Path

SITE_FILES = ("index.html", "robots.txt", "sitemap.xml", "styles.css", "zh-CN/index.html")
BRAND_FILES = (
    ("assets/brand/signetum-mark.png", "assets/signetum-mark.png"),
    ("assets/brand/signetum-social-preview.png", "assets/signetum-social-preview.png"),
)


def build_site(repository: Path, destination: Path) -> tuple[str, ...]:
    """Copy the declared site sources and canonical brand assets into a new directory."""
    if destination.exists():
        raise ValueError(f"site destination must not exist: {destination}")
    sources = tuple((repository / "site" / name, name) for name in SITE_FILES) + tuple(
        (repository / source, target) for source, target in BRAND_FILES
    )
    missing = [str(source) for source, _ in sources if not source.is_file()]
    if missing:
        raise ValueError(f"site source is incomplete: {', '.join(missing)}")

    for source, target in sources:
        output = destination / target
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
    return tuple(sorted(target for _, target in sources))
