"""Check the tracked, repository-relative public documentation surface."""

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from yaml import YAMLError, safe_load

from signetum.change.models import require_relative_path
from signetum.contract_values import FrozenContract
from signetum.traceability.boundary import RepositoryInventory

REQUIRED_PRODUCT_PATHS = (
    "README.md",
    "QUICKSTART.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "LICENSE",
    "assets/brand/signetum-mark.svg",
    "assets/brand/signetum-social-preview.png",
    "site/index.html",
    "site/zh-CN/index.html",
    "site/styles.css",
    "site/robots.txt",
    "site/sitemap.xml",
    ".github/workflows/pages.yml",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "docs/ARCHITECTURE.md",
    "docs/README.md",
    "docs/guide.md",
    "docs/decisions/README.md",
    "docs/guides/repository-bindings.md",
    "docs/maintainers/releasing.md",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
)

REQUIRED_PRODUCT_CONTENT: dict[str, tuple[str, ...]] = {}

_MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


@dataclass(frozen=True, kw_only=True)
class ProductSurfaceIssue(FrozenContract):
    code: str
    source: str
    target: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class ProductSurfaceReport(FrozenContract):
    schema_version: int = 1
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
    issues.extend(_workflow_issues(repository, inventory))
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


def _workflow_issues(repository: Path, inventory: RepositoryInventory) -> list[ProductSurfaceIssue]:
    """Existing public-surface checks own structured workflow safety constraints."""
    issues = []
    for relative in sorted(inventory.paths):
        composite = relative.startswith(".github/actions/") and PurePosixPath(relative).name in {
            "action.yml",
            "action.yaml",
        }
        if not composite and not (
            relative.startswith(".github/workflows/") and relative.endswith((".yml", ".yaml"))
        ):
            continue
        try:
            document = safe_load((repository / relative).read_text())
            if not isinstance(document, dict):
                raise ValueError("workflow or action must declare an object")
            if composite:
                runs = document.get("runs", {})
                if not isinstance(runs, dict) or runs.get("using") != "composite":
                    raise ValueError("local action must declare composite steps")
                jobs = {"composite": runs}
            else:
                jobs = document.get("jobs")
                if not isinstance(jobs, dict):
                    raise ValueError("workflow must declare a jobs object")
            for job in jobs.values():
                if not isinstance(job, dict) or not isinstance(job.get("steps", []), list):
                    raise ValueError("workflow job and steps have invalid shapes")
                if PurePosixPath(relative).name == "ci.yml":
                    permissions = job.get("permissions", document.get("permissions"))
                    if permissions != "read-all" and (
                        not isinstance(permissions, dict)
                        or any(level not in ("read", "none") for level in permissions.values())
                    ):
                        raise ValueError("CI permissions must remain explicitly read-only")
                steps = list(job.get("steps", []))
                if "uses" in job:
                    steps.append({"uses": job["uses"]})
                for step in steps:
                    if not isinstance(step, dict):
                        raise ValueError("workflow step must be an object")
                    action = step.get("uses")
                    if action is None:
                        continue
                    if not isinstance(action, str) or (
                        not action.startswith("./")
                        and not re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", action)
                    ):
                        raise ValueError("external actions require exact commit identities")
                    if action.lower().startswith("actions/checkout@"):
                        settings = step.get("with", {})
                        if (
                            not isinstance(settings, dict)
                            or settings.get("ref") != "${{ github.sha }}"
                        ):
                            raise ValueError("checkout must observe the exact triggering commit")
        except (OSError, YAMLError, ValueError) as error:
            issues.append(
                ProductSurfaceIssue(
                    code="invalid-workflow-policy",
                    source=relative,
                    target=relative,
                    reason=str(error),
                )
            )
    return issues
