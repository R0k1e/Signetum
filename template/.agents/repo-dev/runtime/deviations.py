"""Run the generated Signetum ledger and review authority."""

import sys
from pathlib import Path

# Bootstrap must disable bytecode before loading the portable runtime.
sys.dont_write_bytecode = True

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _signetum_runtime.deviations import (  # noqa: E402
    DeviationError,
    approval_view,
    main,
    reconciliation_summary,
)

__all__ = ["DeviationError", "approval_view", "main", "reconciliation_summary"]


if __name__ == "__main__":
    raise SystemExit(main())
