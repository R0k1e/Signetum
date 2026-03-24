"""Pytest configuration and Hypothesis profiles.

Profiles:
  dev (default): 50 examples — fast enough for pre-commit and local runs.
  ci: 500 examples — deep corner-case search, runs in CI only.

Activate CI profile by setting HYPOTHESIS_PROFILE=ci in the environment.
"""

import os

from hypothesis import HealthCheck
from hypothesis import settings

settings.register_profile(
    "ci",
    max_examples=500,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile("dev", max_examples=50)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))
