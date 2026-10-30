"""Strict reconstruction of portable dataclass wire values from their owned types."""

import json
import math
from dataclasses import MISSING, dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from functools import cache
from re import fullmatch
from types import UnionType
from typing import (
    Annotated,
    Literal,
    NoReturn,
    TypeAliasType,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

type JsonValue = dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None


class ValueDecodeError(ValueError):
    """A serialized value does not have its declared structure or primitive type."""


@cache
def _annotations(model: type) -> dict[str, object]:
    return get_type_hints(model, include_extras=True)


@dataclass(frozen=True)
class Constraints:
    """Field restrictions owned by portable contract declarations."""

    min_length: int | None = None
    pattern: str | None = None
    minimum: int | None = None

    def check(self, value: object, location: str) -> None:
        if value is None:
            return
        if self.min_length is not None and (
            not isinstance(value, (str, tuple, list)) or len(value) < self.min_length
        ):
            raise ValueDecodeError(f"{location}: value must have minimum length {self.min_length}")
        if self.pattern is not None and (
            not isinstance(value, str) or fullmatch(self.pattern, value) is None
        ):
            raise ValueDecodeError(f"{location}: value does not match its declared pattern")
        if self.minimum is not None and (type(value) is not int or value < self.minimum):
            raise ValueDecodeError(f"{location}: value must be at least {self.minimum}")


def _decode(
    value: object, expected: object, location: str, use_defaults: bool, *, native: bool = False
) -> object:
    if isinstance(expected, TypeAliasType):
        return _decode(value, expected.__value__, location, use_defaults, native=native)
    origin = get_origin(expected)
    arguments = get_args(expected)
    if origin is Annotated:
        decoded = _decode(value, arguments[0], location, use_defaults, native=native)
        for restriction in arguments[1:]:
            if not isinstance(restriction, Constraints):
                raise ValueDecodeError(f"{location}: unsupported contract restriction")
            restriction.check(decoded, location)
        return decoded
    if origin is Literal:
        if any(type(value) is type(item) and value == item for item in arguments):
            return value
        raise ValueDecodeError(f"{location}: value does not match the declared literal")
    if origin in (UnionType, Union):
        for alternative in arguments:
            try:
                return _decode(value, alternative, location, use_defaults, native=native)
            except ValueDecodeError:
                pass
        raise ValueDecodeError(f"{location}: value does not match the declared alternatives")
    if isinstance(expected, type) and is_dataclass(expected):
        model_fields = fields(expected)
        names = {field.name for field in model_fields}
        if native:
            if type(value) is not expected:
                raise ValueDecodeError(f"{location}: invalid native contract type")
            document = {field.name: getattr(value, field.name) for field in model_fields}
        else:
            document = value
        if not isinstance(document, dict) or (not use_defaults and set(document) != names):
            raise ValueDecodeError(f"{location}: invalid dataclass fields")
        annotations = _annotations(expected)
        values = {}
        for field in model_fields:
            if field.name not in document:
                if use_defaults and (
                    field.default is not MISSING or field.default_factory is not MISSING
                ):
                    continue
                raise ValueDecodeError(f"{location}: missing field {field.name}")
            values[field.name] = _decode(
                document[field.name],
                annotations[field.name],
                f"{location}.{field.name}",
                use_defaults,
                native=native,
            )
        if set(document) - names:
            raise ValueDecodeError(f"{location}: unknown dataclass fields")
        return value if native else expected(**values)
    if isinstance(expected, type) and issubclass(expected, Enum):
        if type(value) is expected:
            return value
        if not native and type(value) is str:
            try:
                return expected(value)
            except ValueError:
                pass
        raise ValueDecodeError(f"{location}: invalid declared enum value")
    if expected in (date, datetime):
        if type(value) is expected:
            return value
        if not native and type(value) is str:
            try:
                return (
                    date.fromisoformat(value) if expected is date else datetime.fromisoformat(value)
                )
            except ValueError:
                pass
        raise ValueDecodeError(f"{location}: invalid declared date value")
    if origin in (tuple, frozenset):
        item_type = arguments[0]
        if origin is tuple and (len(arguments) != 2 or arguments[1] is not Ellipsis):
            raise ValueDecodeError(f"{location}: unsupported tuple declaration")
        if not isinstance(value, (list, tuple, frozenset)):
            raise ValueDecodeError(f"{location}: expected an array")
        if native and type(value) is not origin:
            raise ValueDecodeError(f"{location}: invalid native collection type")
        if not native and origin is tuple and isinstance(value, frozenset):
            raise ValueDecodeError(f"{location}: expected an ordered array")
        items = [
            _decode(item, item_type, f"{location}[{index}]", use_defaults, native=native)
            for index, item in enumerate(value)
        ]
        return tuple(items) if origin is tuple else frozenset(items)
    if origin is list:
        if not isinstance(value, list):
            raise ValueDecodeError(f"{location}: expected an array")
        return [
            _decode(item, arguments[0], f"{location}[{index}]", use_defaults, native=native)
            for index, item in enumerate(value)
        ]
    if origin is dict:
        if not isinstance(value, dict):
            raise ValueDecodeError(f"{location}: expected an object")
        return {
            _decode(key, arguments[0], location, use_defaults, native=native): _decode(
                item, arguments[1], f"{location}.{key}", use_defaults, native=native
            )
            for key, item in value.items()
        }
    if expected in (str, int, float, bool, type(None)) and type(value) is expected:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueDecodeError(f"{location}: non-finite JSON number")
        return value
    raise ValueDecodeError(f"{location}: invalid declared value type")


def validate_dataclass(value: object) -> None:
    """Apply the owned field types and restrictions to direct construction too."""
    if not is_dataclass(value) or isinstance(value, type):
        raise ValueDecodeError("contract value must be a dataclass instance")
    _decode(value, type(value), "$", False, native=True)


def validate_value(value: object, expected: object) -> None:
    """Apply a declared field boundary without coercing its native value."""
    _decode(value, expected, "$", False, native=True)


def json_value(value: object) -> JsonValue:
    """Project portable contract values without leaking host or library objects."""
    if isinstance(value, Enum):
        return json_value(value.value)
    if isinstance(value, datetime):
        rendered = value.isoformat()
        return rendered[:-6] + "Z" if rendered.endswith("+00:00") else rendered
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return contract_mapping(value)
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    if isinstance(value, frozenset):
        return [json_value(item) for item in sorted(value)]
    if isinstance(value, dict) and all(type(key) is str for key in value):
        return {key: json_value(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueDecodeError("non-finite JSON number")
        return value
    raise ValueDecodeError("unsupported contract JSON value")


def contract_mapping(value: object) -> dict[str, JsonValue]:
    """Project one typed contract while retaining its object result type."""
    if not is_dataclass(value) or isinstance(value, type):
        raise ValueDecodeError("contract value must be a dataclass instance")
    return {field.name: json_value(getattr(value, field.name)) for field in fields(value)}


def dataclass_from_mapping[T](model: type[T], value: object, *, use_defaults: bool = False) -> T:
    """Decode owned types; only configuration readers explicitly permit defaults."""
    if not is_dataclass(model):
        raise ValueDecodeError("wire model must be a dataclass")
    result = _decode(value, model, "$", use_defaults)
    if not isinstance(result, model):
        raise ValueDecodeError("decoded value has an unexpected model")
    return result


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise ValueDecodeError(f"duplicate JSON field: {name}")
        result[name] = value
    return result


def load_json(source: str) -> object:
    """Retain duplicate-field ambiguity as an error before constructing values."""
    if not isinstance(source, str):
        raise ValueDecodeError("JSON source must be text")

    def constant(value: str) -> NoReturn:
        raise ValueDecodeError(f"non-finite JSON number: {value}")

    def number(value: str) -> float:
        result = float(value)
        if not math.isfinite(result):
            constant(value)
        return result

    try:
        return json.loads(
            source, object_pairs_hook=_unique_object, parse_constant=constant, parse_float=number
        )
    except RecursionError as error:
        raise ValueDecodeError("JSON nesting exceeds the supported depth") from error
