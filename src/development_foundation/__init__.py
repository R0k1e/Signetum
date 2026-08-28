"""Versioned repository-development foundation."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("development-foundation")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]
