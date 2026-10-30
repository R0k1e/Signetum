"""Run the generated repository-owned protocol utility."""

import sys
from pathlib import Path

# Bootstrap must disable bytecode before loading the portable runtime.
sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _signetum_runtime.protocol_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
