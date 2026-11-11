"""Final's versioned exact-source handoff to lightweight publication."""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from signetum.execution_review import ExecutionReviewInputs
from signetum.git import git_output, run_git
from signetum.operations import AdmissionError
from signetum.policy import delivery_policy
from signetum.serialization import dataclass_from_mapping
from signetum.workspaces import branch_name, record_path, state_root


def document_digest(document: object) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return "absent"


def _legacy_digest(root: Path, members: list[str], changes: list[str]) -> str:
    """Fingerprint relevant legacy bytes, including newly introduced ledgers."""
    selected = {}
    names = tuple(json.dumps(member).encode() for member in members)
    for path in (root / "changes").glob("*/deviations.jsonl"):
        data = path.read_bytes()
        if path.parent.name in changes or any(name in data for name in names):
            selected[path.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()
    return document_digest(selected)


def _remote_digest(repository: Path) -> str:
    result = run_git(repository, "remote", "get-url", "--push", "--all", "origin")
    return document_digest((result.returncode, result.stdout))


def review_local_inputs(
    repository: Path, inputs: ExecutionReviewInputs, receipt_root: Path
) -> dict[str, str]:
    """Bind admitted evidence and workspace authority without reading source history."""
    root = state_root(repository)
    paths = [record_path(root, branch_name(repository))]
    for row in inputs["member_chain"]:
        branch = row["member"]
        if not isinstance(branch, str):
            raise AdmissionError("review member identity is invalid")
        paths.append(record_path(root, branch))
    paths.extend(receipt_root / name for name in inputs["member_evidence"])
    return {
        **{path.relative_to(root).as_posix(): _file_digest(path) for path in paths},
        "legacy-discoveries": _legacy_digest(root, inputs["members"], inputs["changes"]),
        "publication-remote": _remote_digest(repository),
    }


@dataclass(frozen=True)
class PublicationBinding:
    """Only final constructs this handoff after the complete verdict."""

    schema_version: Literal[1]
    source: str
    base: str
    target_branch: str
    review_digest: str
    evidence_digest: str
    authorization_digest: str
    local_inputs: dict[str, str]
    members: list[dict[str, str]]
    plans: list[str]

    def document(self) -> dict[str, object]:
        return asdict(self)


def bind_publication(
    repository: Path,
    *,
    source: str,
    base: str,
    review: object,
    evidence: object,
    local_inputs: dict[str, str],
    members: list[dict[str, str]],
    plans: list[str],
    authorization: object = None,
) -> PublicationBinding:
    return PublicationBinding(
        schema_version=1,
        source=source,
        base=base,
        target_branch=delivery_policy(repository).branch,
        review_digest=document_digest(review),
        evidence_digest=document_digest(evidence),
        authorization_digest=document_digest(authorization),
        local_inputs=local_inputs,
        members=members,
        plans=plans,
    )


def require_publication_binding(
    repository: Path, payload: dict[str, object], *, source: str, base: str
) -> PublicationBinding:
    document = payload.get("publication_binding")
    if document is None:
        raise AdmissionError("final receipt has no versioned publication binding; rerun final")
    try:
        binding = dataclass_from_mapping(PublicationBinding, document)
    except (TypeError, ValueError) as error:
        raise AdmissionError(f"invalid publication binding; rerun final: {error}") from error
    if (
        binding.source != source
        or binding.base != base
        or binding.target_branch != delivery_policy(repository).branch
        or binding.review_digest != document_digest(payload.get("delivery_review"))
        or binding.evidence_digest != document_digest(payload.get("evidence"))
        or binding.authorization_digest != document_digest(payload.get("delivery_authorization"))
    ):
        raise AdmissionError("final publication binding changed; rerun final")
    root = state_root(repository)
    for name, expected in binding.local_inputs.items():
        if name == "publication-remote":
            if _remote_digest(repository) != expected:
                raise AdmissionError("publication remote changed; rerun final")
            continue
        if name == "legacy-discoveries":
            review = payload.get("delivery_review")
            inputs = review.get("inputs") if isinstance(review, dict) else None
            members = inputs.get("members") if isinstance(inputs, dict) else None
            changes = inputs.get("changes") if isinstance(inputs, dict) else None
            if (
                not isinstance(members, list)
                or not all(isinstance(member, str) for member in members)
                or not isinstance(changes, list)
                or not all(isinstance(change, str) for change in changes)
                or _legacy_digest(root, members, changes) != expected
            ):
                raise AdmissionError("delivery review inputs changed; rerun final")
            continue
        relative = PurePosixPath(name)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not relative.parts
            or relative.parts[0] not in {"validation", "workspaces"}
        ):
            raise AdmissionError("invalid publication input path; rerun final")
        if _file_digest(root / name) != expected:
            raise AdmissionError(f"publication input changed: {name}; rerun final")
    if git_output(repository, "rev-parse", "HEAD") != source:
        raise AdmissionError("source tip differs from the final publication binding")
    return binding
