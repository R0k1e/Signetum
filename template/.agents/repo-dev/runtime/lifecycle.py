"""Run the generated Signetum lifecycle authority."""

import sys

sys.dont_write_bytecode = True
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _signetum_runtime.lifecycle import main

if __name__ == "__main__":
    raise SystemExit(main())
