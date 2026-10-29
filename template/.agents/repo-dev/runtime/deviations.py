"""Run the generated Signetum ledger and review authority."""

import sys

sys.dont_write_bytecode = True
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _signetum_runtime.deviations import (
    DeviationError,
    approval_view,
    main,
    reconciliation_summary,
)

__all__ = ["DeviationError", "approval_view", "main", "reconciliation_summary"]


if __name__ == "__main__":
    raise SystemExit(main())
