"""Run the generated Signetum change and relation authority."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _signetum_runtime.traceability_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
