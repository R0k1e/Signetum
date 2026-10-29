# Generated from signetum.selection_request; edit the engine source and regenerate.
"""Typed selection request values layered above manifest declarations."""

from dataclasses import dataclass
from typing import Annotated, Literal

from .contract_values import FrozenContract
from .decision_clauses import Text
from .evidence_receipts import ArtifactIdentity, ToolIdentity
from .serialization import Constraints
from .validation import ValidationGraph


@dataclass(frozen=True, kw_only=True)
class SelectionInput(FrozenContract):
    artifact: ArtifactIdentity
    blob: Text


@dataclass(frozen=True, kw_only=True)
class SelectionRequest(FrozenContract):
    protocol: Literal["signetum.selection@1"]
    source: Text
    tree: Text
    base: Text
    files: tuple[Text, ...]
    graph: ValidationGraph
    profiles: tuple[Text, ...]
    inputs: tuple[SelectionInput, ...]
    tools: tuple[ToolIdentity, ...]
    request_digest: Annotated[str, Constraints(pattern="^sha256:[0-9a-f]{64}$")] = (
        "sha256:" + "0" * 64
    )
