"""Untrusted receipt documents obey the owned types in both distributed forms."""

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from test_receipts_v2 import _gate, _identity, _selection

from signetum.evidence.receipts import EvidenceReceipt, ReceiptError


@pytest.fixture(params=["engine", "generated"])
def decode(request):
    if request.param == "engine":
        return lambda source: json.loads(EvidenceReceipt.from_json(source).to_json())
    runtime = Path(__file__).parents[3] / "template/.agents/repo-dev/runtime"
    script = """
import sys
sys.path.insert(0,sys.argv[1])
from _signetum_runtime.evidence_receipts import EvidenceReceipt,ReceiptError
try:
    result=EvidenceReceipt.from_json(sys.stdin.read())
except ReceiptError as error:
    print(str(error),file=sys.stderr)
    raise SystemExit(2)
assert 'signetum' not in sys.modules and 'pydantic' not in sys.modules
print(result.to_json(),end='')
"""

    def generated(source):
        result = subprocess.run(  # noqa: S603 -- isolated generated consumer, source via stdin
            [sys.executable, "-I", "-S", "-c", script, str(runtime)],
            input=source,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode in {0, 2}, result.stderr
        if result.returncode == 2:
            raise ReceiptError(result.stderr)
        return json.loads(result.stdout)

    return generated


@pytest.fixture
def document():
    receipt = replace(_gate(_identity(), "member", ("core:static",)), selection=_selection())
    return json.loads(receipt.to_json())


@pytest.mark.parametrize(
    "path,value",
    [
        (("extensions",), "not-an-object"),
        (("extensions",), []),
        (("valid",), "yes"),
        (("valid",), 1),
        (("schema_version",), 3.0),
        (("identity", "profiles"), "python-default@2"),
        (("identity", "tools"), {}),
        (("identity", "tools", 0, "identity"), 17),
        (("identity", "configuration", "digest"), True),
        (("identity", "lockfiles", 0, "path"), 17),
        (("execution", "gates"), "member"),
        (("execution", "gates"), [17]),
        (("execution", "shards"), {}),
        (("execution", "external_obligations"), "external"),
        (("execution", "external_obligations"), ["same", "same"]),
        (("completeness", "member"), "yes"),
        (("completeness", "final"), 1),
        (("completeness", "required_shards"), "core:static"),
        (("completeness", "required_shards"), ["same", "same"]),
        (("completeness", "world_shards"), [False]),
        (("selection", "requires_final"), "false"),
        (("selection", "shards"), "core:static"),
        (("extensions",), {"nested": [float("nan")]}),
        (("extensions",), {"nested": {"number": float("inf")}}),
    ],
)
def test_wrong_scalar_or_collection_never_becomes_receipt_evidence(decode, document, path, value):
    target = document
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(ReceiptError):
        decode(json.dumps(document))


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("identity",),
        ("identity", "configuration"),
        ("identity", "tools", 0),
        ("selection",),
        ("execution",),
        ("execution", "shards", 0),
        ("completeness",),
        ("provenance",),
    ],
)
def test_unknown_fields_are_not_silently_discarded(decode, document, path):
    target = document
    for part in path:
        target = target[part]
    target["unbound"] = "not declared"
    with pytest.raises(ReceiptError):
        decode(json.dumps(document))


@pytest.mark.parametrize(
    "path", [("provenance", "stable_patch_id"), ("execution", "shards", 0, "observed_at")]
)
def test_wire_required_fields_are_not_filled_from_constructor_defaults(decode, document, path):
    target = document
    for part in path[:-1]:
        target = target[part]
    del target[path[-1]]
    with pytest.raises(ReceiptError):
        decode(json.dumps(document))


@pytest.mark.parametrize("field", ["commit", "tree", "base"])
@pytest.mark.parametrize("length", [39, 41, 63, 65])
def test_git_object_ids_have_exact_algorithm_lengths(decode, document, field, length):
    document["identity"][field] = "a" * length
    with pytest.raises(ReceiptError):
        decode(json.dumps(document))


def test_duplicate_keys_are_not_resolved_by_last_value_wins(decode, document):
    source = json.dumps(document)[:-1] + ',"valid":false,"valid":true}'
    with pytest.raises(ReceiptError):
        decode(source)


def test_deep_invalid_input_is_reported_at_the_receipt_boundary(decode):
    with pytest.raises(ReceiptError):
        decode("[" * 1200 + "0" + "]" * 1200)


@pytest.mark.parametrize("length", [40, 64])
@pytest.mark.parametrize("selected", [True, False])
def test_complete_values_and_free_json_extensions_round_trip(decode, document, length, selected):
    for field in ("commit", "tree", "base"):
        document["identity"][field] = "a" * length
    document["selection"] = document["selection"] if selected else None
    document["extensions"] = {"values": [None, False, 5, 1.5, "text", {"nested": []}]}
    assert decode(json.dumps(document)) == document


@pytest.mark.parametrize(
    "change",
    [
        {"extensions": "not-an-object"},
        {"extensions": {"key": float("nan")}},
        {"extensions": {1: "not-a-string-key"}},
        {"selection": replace(_selection(), requires_final="yes")},
    ],
)
def test_programmatic_invalid_values_are_not_written_as_receipts(change):
    receipt = replace(_gate(_identity(), "member", ("core:static",)), **change)
    with pytest.raises(ReceiptError):
        receipt.to_json()
