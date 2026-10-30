"""Bind this repository to the optional committed Python reach provider."""

from signetum.python_selection import main

if __name__ == "__main__":
    raise SystemExit(main(["--config", ".agents/repo-dev/python-selection.json"]))
