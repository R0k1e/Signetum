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
| **VS Code Config** | IDE Integration | Configures the default Python interpreter (`.venv`) and sets Ruff as the default on-save formatter for a unified development experience. | (`.vscode/settings.json`) |

# Directory Structure
``` bash
your-project/
├── .env.example
├── .github
│   └── workflows
│       └── ci.yml
├── .gitignore
├── .pre-commit-config.yaml
├── .python-version
├── .vscode
│   └── settings.json
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── config
│   └── config.yml
├── main.py
├── pyproject.toml
├── scripts
│   └── init_repo.sh
├── src
│   └── placeholder_name
│       ├── __init__.py
│       └── py.typed
└── tests
    └── test_smoke.py
```
