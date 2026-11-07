"""Delivery facts have one repository-owned manifest authority."""

from pathlib import Path

from signetum.git import git_output
from signetum.manifest import DeliveryBindings, ManifestError, load_bindings


def delivery_policy(repository: Path) -> DeliveryBindings:
    delivery = load_bindings(repository / "signetum.toml").delivery
    if delivery is None:
        raise ManifestError("declare delivery.branch in signetum.toml")
    git_output(repository, "check-ref-format", "--branch", delivery.branch)
    return delivery
