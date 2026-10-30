# Portable runtime acceptance fixture

Internal scaffold for Signetum rendering and independent runtime tests. This is
not a public project-creation route. Users install `skills/signetum` and review
local adoption with their existing application tools.

The renderer combines these small fixture files with a portable runtime generated
from the maintained engine. Generated modules are ignored build/test output.
See the product repository's architecture and contributor guide for maintenance.

`uv.lock` pins this fixture's isolated Python test tools for `uv sync --locked`.
It is not needed to install the Skill and adoption does not copy this fixture.
