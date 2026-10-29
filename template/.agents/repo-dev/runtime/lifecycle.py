"""Run the generated Signetum lifecycle authority."""

import sys
from pathlib import Path

# Bootstrap must disable bytecode before loading the portable runtime.
sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _signetum_runtime.lifecycle import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
