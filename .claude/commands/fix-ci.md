Fetch the latest CI failure logs for the current branch and fix all issues.

Steps:
1. Run `git branch --show-current` to get the current branch name.
2. Run `gh run list --branch <branch> --workflow ci.yml --status failure --limit 1 --json databaseId,displayTitle,createdAt` to find the latest failed run. If no failed run is found, report that CI is green and stop.
3. Run `gh run view <run-id> --log-failed` to get the full failure logs.
4. Analyse the logs to identify every failing check and its root cause.
5. Fix each issue. Common categories and their resolution commands:
   - Ruff lint/format:  `uv run ruff check --fix src main.py && uv run ruff format src main.py`
   - Type errors (ty):  read the flagged lines, fix the source files directly
   - Dead code:         `uv run vulture src main.py --min-confidence 80` — remove or wire up the unused code
   - Test failures:     read each failing test, fix the source (never weaken the test to make it pass)
   - import-linter:     `uv run lint-imports` — fix the architectural dependency violation in source
   - Bandit SAST:       `uv run bandit -r src` — fix the security issue in source
   - Typos:             fix the misspelled words in the flagged files
6. Verify the full fix locally before finishing:
   `uv run ruff check src main.py && uv run ty check src && uv run vulture src main.py --min-confidence 80 && uv run lint-imports && uv run pytest -m "not slow" --no-cov`
7. Print a concise summary: which checks failed, what was changed, verification result.
