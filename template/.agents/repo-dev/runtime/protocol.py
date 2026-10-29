"""Run the generated repository-owned protocol utility."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _signetum_runtime.protocol_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
