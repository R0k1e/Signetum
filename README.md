# Python CI Repo Template

This repository serves as a robust project template for high-performance and reproducible Python development, enforcing code quality, style, and type safety through an automated Continuous Integration pipeline.

# Usage
1. Use this template to create new repo
2. Clone the new repo
3. Execute this script. The package name will be renamed as the directory name.

``` bash
pip install uv
uv sync
uv run pre-commit autoupdate --repo https://github.com/pre-commit/pre-commit-hooks
bash scirpt/init_repo.sh
```

## Stack Overview

| Component | Category | Purpose | Reference |
| :--- | :--- | :--- | :--- |
| **uv** | Dependency Manager | Extremely fast dependency resolution, environment creation, and execution (combining the functionalities of `pip`, `venv`, and `pip-tools`). | [astral-sh/uv](https://github.com/astral-sh/uv) |
| **Ruff** | Linter & Formatter | An all-in-one Rust-based tool for high-speed code style enforcement, linting, and `import` sorting. | [astral-sh/ruff](https://github.com/astral-sh/ruff) |
| **MyPy** | Type Checker | Statically analyzes code to ensure all type annotations are consistent and accurate, preventing runtime type errors. | [python/mypy](https://github.com/python/mypy) |
| **Pytest** | Testing Framework | The standard framework used for running unit and integration tests within the CI pipeline. | [pytest-dev/pytest](https://github.com/pytest-dev/pytest) |
| **Pre-commit** | Local Hooks | A framework that automatically runs Ruff, MyPy, and other checks on staged files *before* a commit is finalized, ensuring local compliance. | [pre-commit/pre-commit](https://github.com/pre-commit/pre-commit) |
| **GitHub Workflow (CI)** | Automation | Defines the cloud-based quality gate, running all checks across a Python version matrix (`3.10`, `3.11`, `3.12`) to ensure cross-version compatibility. | (`.github/workflows/ci.yml`) |
| **Hatchling** | Build Backend | Modern build backend for Python packages, used to build wheel and source distributions. | [pypa/hatchling](https://github.com/pypa/hatchling) |
| **hatch-vcs** | Version Management | Automatically extracts version numbers from git tags, eliminating manual version updates. | [ofek/hatch-vcs](https://github.com/ofek/hatch-vcs) |
| **GitHub Workflow (CD)** | Automation | Automatically builds and publishes packages to PyPI and GitHub Releases when a git tag is pushed. | (`.github/workflows/cd.yml`) |
| **VS Code Config** | IDE Integration | Configures the default Python interpreter (`.venv`) and sets Ruff as the default on-save formatter for a unified development experience. | (`.vscode/settings.json`) |

# Directory Structure
``` bash
your-project/
├── .env.example
├── .github
│   └── workflows
│       ├── ci.yml
│       └── cd.yml
├── .gitignore
├── .pre-commit-config.yaml
├── .python-version
├── .vscode
│   └── settings.json
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── config
│   └── config.yml
├── main.py
├── pyproject.toml
├── scripts
│   ├── extract_release_notes.py
│   └── init_repo.sh
├── src
│   └── placeholder_name
│       ├── __init__.py
│       └── py.typed
└── tests
    └── test_smoke.py
```

# Release Process

This template includes a complete Continuous Deployment (CD) pipeline that automatically builds and publishes packages when you push a git tag.

## How to Release

### Step 1: Prepare Release Notes

You have two options for providing release notes:

**Option A: Use CHANGELOG.md (Recommended)**
1. Update `CHANGELOG.md` with the new version entry:
   ```markdown
   ## [v1.0.0] - 2024-01-01
   
   ### Added
   - New feature X
   - New feature Y
   
   ### Fixed
   - Fixed bug Z
   ```

**Option B: Use Git Tag Annotation**
1. Create an annotated tag with release notes:
   ```bash
   git tag -a v1.0.0 -m "Release v1.0.0
   
   New features:
   - Feature X
   - Feature Y
   
   Fixes:
   - Bug Z"
   ```

### Step 2: Create and Push Tag

```bash
# If you haven't created the tag yet (Option B)
git tag -a v1.0.0 -m "Release v1.0.0"

# Push the tag to trigger CD
git push origin v1.0.0
```

### Step 3: Automatic Deployment

The CD workflow will automatically:
1. ✅ Extract version from git tag (using `hatch-vcs`)
2. ✅ Extract release notes from CHANGELOG.md or tag annotation
3. ✅ Build package (wheel and source distribution) using `hatchling`
4. ✅ Publish to PyPI (if `PYPI_API_TOKEN` is configured)
5. ✅ Create GitHub Release with build artifacts

## Configuration

### PyPI Publishing

To enable PyPI publishing, add a `PYPI_API_TOKEN` secret to your GitHub repository:

1. Go to your repository Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: `PYPI_API_TOKEN`
4. Value: Your PyPI API token (get it from [pypi.org/manage/account/token/](https://pypi.org/manage/account/token/))
5. Click "Add secret"

**Note**: If `PYPI_API_TOKEN` is not set, the CD workflow will skip PyPI publishing but still create a GitHub Release.

## Version Management

The project uses `hatch-vcs` to automatically extract version numbers from git tags:
- Version is set dynamically in `pyproject.toml` via `dynamic = ["version"]`
- No need to manually update version numbers
- Version format: `v1.0.0` or `1.0.0` (both are supported)
