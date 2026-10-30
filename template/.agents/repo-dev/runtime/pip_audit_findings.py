"""Run the generated Python audit adapter without installing the engine."""

import sys
from pathlib import Path

# Bootstrap must disable bytecode before loading the portable runtime.
sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _signetum_runtime.findings import FindingsError  # noqa: E402
from _signetum_runtime.pip_audit import report  # noqa: E402


def main() -> int:
    try:
        print(report())
    except FindingsError as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
