"""Entry point.

Installs uvloop and loads .env before delegating to the CLI adapter.
Side effects (env, event loop) are isolated here — adapters stay pure.
"""

import uvloop
from dotenv import load_dotenv

from placeholder_name.adapters.cli import app

load_dotenv()
uvloop.install()

if __name__ == "__main__":
    app()
