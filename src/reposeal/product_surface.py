"""Check the tracked, repository-relative public documentation surface."""

import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from pydantic import Field

from reposeal.change.models import FrozenModel, require_relative_path
from reposeal.traceability.boundary import RepositoryInventory

REQUIRED_PRODUCT_PATHS = (
    "README.md",
    "QUICKSTART.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "LICENSE",
    "assets/brand/reposeal-mark.png",
    "assets/brand/reposeal-mark-512.png",
    "assets/brand/reposeal-mark-256.png",
    "assets/brand/reposeal-mark-128.png",
    "assets/brand/reposeal-mark-64.png",
    "assets/brand/reposeal-mark-32.png",
    "assets/brand/reposeal-social-preview.png",
    "site/index.html",
    "site/zh-CN/index.html",
    "site/styles.css",
    "site/robots.txt",
    "site/sitemap.xml",
    ".github/workflows/pages.yml",
    "docs/ARCHITECTURE.md",
    "docs/README.md",
    "docs/decisions/README.md",
    "docs/concepts/development-lifecycle.md",
    "docs/product/why-reposeal.md",
    "docs/product/frequently-asked-questions.md",
    "docs/product/reposeal-and-specification-tools.md",
    "docs/workflows/agent-team-delivery.md",
    "docs/guides/customizing-the-template.md",
    "docs/maintainers/releasing.md",
    "examples/complete-change/README.md",
    "examples/complete-change/review.yaml",
    "examples/complete-change/specs/greeting.yaml",
    "examples/complete-change/plans/greeting.md",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
)

REQUIRED_PRODUCT_CONTENT = {
    "README.md": ("# RepoSeal", "Seal every change with evidence"),
    "QUICKSTART.md": ("RepoSeal",),
    "docs/product/why-reposeal.md": ("# Why RepoSeal exists",),
    "docs/product/frequently-asked-questions.md": ("## What is RepoSeal?",),
}

_MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


class ProductSurfaceIssue(FrozenModel):
    code: str
    source: str
    target: str
    reason: str


class ProductSurfaceReport(FrozenModel):
    schema_version: int = Field(default=1)
    valid: bool
    issues: tuple[ProductSurfaceIssue, ...]


def validate_product_surface(
    repository: Path,
    inventory: RepositoryInventory,
    *,
    required_paths: tuple[str, ...] = REQUIRED_PRODUCT_PATHS,
    required_content: dict[str, tuple[str, ...]] = REQUIRED_PRODUCT_CONTENT,
) -> ProductSurfaceReport:
    """Validate required assets and local links against one captured inventory."""
    issues: list[ProductSurfaceIssue] = []
    for required in required_paths:
        if not inventory.contains(required):
            issues.append(
                ProductSurfaceIssue(
                    code="missing-required-asset",
                    source="product-surface",
                    target=required,
                    reason="required public product asset is absent",
                )
            )

    for source, fragments in required_content.items():
        if not inventory.contains(source):
            continue
        document = repository / PurePosixPath(source)
        if not document.is_file():
            continue
        content = document.read_text(encoding="utf-8")
        for fragment in fragments:
            if fragment not in content:
                issues.append(
                    ProductSurfaceIssue(
                        code="missing-required-content",
                        source=source,
                        target=fragment,
                        reason="required public product identity is absent",
                    )
                )

    markdown_paths = sorted(path for path in inventory.paths if path.endswith(".md"))
    for source in markdown_paths:
        document = repository / PurePosixPath(source)
        if not document.is_file():
            continue
        for raw_target in _MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            normalized = _local_target(source, raw_target)
            if normalized is not None and not inventory.contains(normalized):
                issues.append(
                    ProductSurfaceIssue(
                        code="broken-markdown-link",
                        source=source,
                        target=normalized,
                        reason="repository-relative Markdown target is absent",
                    )
                )
    return ProductSurfaceReport(valid=not issues, issues=tuple(issues))


def _local_target(source: str, raw_target: str) -> str | None:
    target = raw_target.strip().strip("<>")
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    decoded = unquote(parsed.path)
    if decoded.startswith("/"):
        return str(require_relative_path(decoded.removeprefix("/")))
    combined = PurePosixPath(source).parent / decoded
    collapsed: list[str] = []
    for part in combined.parts:
        if part == ".":
            continue
        if part == "..":
            if not collapsed:
                return None
            collapsed.pop()
            continue
        collapsed.append(part)
    if not collapsed:
        return None
    return str(require_relative_path("/".join(collapsed)))
