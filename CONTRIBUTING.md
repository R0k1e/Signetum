## 🚀 Developer Quick Start Guide

This project maintains a high engineering standard using the latest Python toolchain (`uv`, `ruff`, MyPy) to ensure quality and environment consistency.

### 1\. Project Initialization (Bootstrap)

The repository uses a **Two-Stage Initialization** process. Ensure you have `git` and `uv` installed locally.

| Step | Command | Purpose |
| :--- | :--- | :--- |
| **1. Clone Repository** | `git clone <repo-url>` | Get the source code. |
| **2. Run Bootstrap** | `cd <repo-name>`<br>`init_repo` | **Required.** This automatically installs dependencies (`uv sync`), replaces template names, and sets up local pre-commit hooks. |

### 2\. Local Development Standards

All code must adhere to the following tools, which are enforced locally before submission.

| Tool | Focus | Local Enforcement | Action if Failed |
| :--- | :--- | :--- | :--- |
| **Ruff (Format/Lint)** | Code Style & Low-Level Bugs | **Automatic** | `pre-commit` will auto-fix simple issues upon `git commit`. |
| **MyPy** | Type Safety & Consistency | **Automatic** | Requires explicit type hints (e.g., `def func(x: int) -> None:`). |
| **Pre-commit** | Commit Gate | **Mandatory** | Runs Ruff and MyPy on staged files. If files are modified by hooks, you must `git add` and `git commit` again. |

### 3\. Quality Gates (CI Requirements)

Code will only be considered for merging if it passes all checks in the GitHub Actions (CI) workflow for all Python versions specified in the matrix (`3.10`, `3.11`, `3.12`).

All checks are run with `continue-on-error: true` to ensure all failures are reported in a single run.

| Check Name | Tool | Purpose |
| :--- | :--- | :--- |
| **Ruff Lint** | `ruff check` | Finds logic/syntax errors and ensures basic compliance. |
| **Ruff Format Check** | `ruff format --check` | Verifies style. Fails if code is not perfectly formatted. |
| **MyPy Type Check** | `mypy src` | Verifies type consistency across the package. |
| **Unit Tests** | `pytest` | Validates core functionality. |

**To fix CI failures, run this locally:**

```bash
uv run ruff check --fix .  # Fixes simple linting errors
uv run ruff format .       # Formats code
uv run mypy src            # Checks for type errors (requires manual fix)
uv run pytest              # Runs tests (requires manual fix)
```
