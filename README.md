# Python CICD Template

A production-ready Python project scaffold built on clean architecture principles. Enforces code quality, type safety, and security through a two-layer quality gate: pre-commit (fast local checks) and CI (deep validation).

## Quick Start

```bash
# 1. Use this template to create a new repo, then clone it
git clone <your-new-repo>
cd <your-new-repo>

# 2. Install uv (if not already installed)
pip install uv

# 3. Run the init script — renames placeholder_name to your package name
bash scripts/init_repo.sh
```

The package name is derived automatically from the repository directory name (`-` → `_`).

## Architecture

Follows clean / onion architecture. Dependency direction is enforced by `import-linter` in CI.

```
main.py                  # entry point — side effects only (uvloop, dotenv)
src/<package>/
  config.py              # Pydantic V2 AppConfig (frozen=True) + LogLevel Enum
  core/
    protocols.py         # typing.Protocol boundaries — no adapter imports allowed
    service.py           # domain logic + icontract pre/post-conditions
    fsm.py               # transitions FSM for complex lifecycle objects
  adapters/
    cli.py               # composition root: Lagom DI + Hydra config + returns at boundary
config/
  config.yml             # Hydra config (name, log_level, output_dir)
tests/
  conftest.py            # Hypothesis profiles: dev (50 examples) / ci (500 examples)
  test_smoke.py
  test_core.py           # @pytest.mark.slow — Hypothesis property tests
  test_config.py         # @pytest.mark.slow — Hypothesis property tests
  test_cli.py            # Typer CliRunner + unittest.mock
```

## Tooling Stack

| Layer | Tool | Role |
| :--- | :--- | :--- |
| Dependency | **uv** | Lock-file management, venv, script runner |
| Lint & Format | **ruff** | E/F/I/B/UP/S/RUF + ANN401 (no `Any`) + PLC0415 (no lazy import) |
| Type Check | **ty** | Static type analysis (Python 3.12) |
| Dead Code | **vulture** | Detects unused functions and variables |
| Contracts | **icontract** | Pre/post-conditions and invariants |
| Error Handling | **returns** | Railway-oriented: `Result`/`Success`/`Failure` at system boundaries |
| DI | **lagom** | Composition root — never injected into domain logic |
| Config | **hydra-core** + **Pydantic V2** | Structured config loaded and validated at boundary |
| Async | **anyio** + **uvloop** | Structured concurrency on asyncio |
| FSM | **transitions** | Explicit state machines — blocks illegal transitions |
| CLI | **typer** | Typed CLI with `--help` generation |
| Logging | **loguru** | Structured logging with rotation |
| Testing | **pytest** + **hypothesis** | Property-based tests; `@pytest.mark.slow` for Hypothesis |
| Architecture | **import-linter** | Enforces core → adapters dependency direction in CI |
| SAST | **bandit** | Static security analysis (CI) |
| SCA | **pip-audit** | Dependency vulnerability scanning |
| Secrets | **detect-secrets** | Blocks credential commits (pre-commit) |
| Spell Check | **typos** | Catches typos in source and docs |
| Build | **hatchling** + **hatch-vcs** | Version from git tags, wheel + sdist |

## Quality Gates

### Pre-commit (fast — runs on every commit)

| Check | Tool |
| :--- | :--- |
| Format fix | ruff (auto-fix) |
| Spell check | typos |
| Secret detection | detect-secrets |
| Type check | ty (modified file) |
| Dead code | vulture |
| Fast unit tests | pytest `-m "not slow"` — no IO, no Hypothesis |
| Dependency audit | pip-audit (on `uv.lock` / `pyproject.toml` changes) |

### CI (deep — runs on every push)

| Job | Checks |
| :--- | :--- |
| `auto-fix` | ruff auto-fix + commit back |
| `test` | pytest full suite, 3.12 (coverage ≥ 80%) + 3.13 (compat); Hypothesis 500 examples |
| `quality-check` | ruff lint, ruff format, ty, vulture, typos, import-linter (× 3.12 + 3.13) |
| `security-check` | pip-audit (SCA) + bandit (SAST) |
| `auto-merge` | merges branch → main on full green; deletes branch |

### Claude Code hooks (runs on every file edit)

- **smoke + ty**: `py_compile` syntax check + `ty` type check on the saved file
- **ruff guard**: `ANN401` (no `Any`), `RUF013` (no implicit `Optional`), `PLC0415` (no lazy import)

## Slash Commands

```
/fix-ci    # fetch latest CI failure logs for current branch and fix all issues
```

## Release

Push a version tag to trigger the CD pipeline:

```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

CD will verify CI passed, build wheel + sdist, publish to PyPI (if `PYPI_API_TOKEN` is set), and create a GitHub Release.

## Directory Structure

```
your-project/
├── .claude/
│   ├── commands/
│   │   └── fix-ci.md
│   └── settings.local.json
├── .env.example
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── cd.yml
├── .pre-commit-config.yaml
├── .python-version
├── .secrets.baseline
├── config/
│   └── config.yml
├── main.py
├── pyproject.toml
├── scripts/
│   └── init_repo.sh
├── src/
│   └── <package>/
│       ├── __init__.py
│       ├── py.typed
│       ├── config.py
│       ├── adapters/
│       │   ├── __init__.py
│       │   └── cli.py
│       └── core/
│           ├── __init__.py
│           ├── fsm.py
│           ├── protocols.py
│           └── service.py
└── tests/
    ├── conftest.py
    ├── test_cli.py
    ├── test_config.py
    ├── test_core.py
    └── test_smoke.py
```
