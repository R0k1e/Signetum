# Generated from signetum.serialization; edit the engine source and regenerate.
"""Strict reconstruction of portable dataclass wire values from their owned types."""

import json
import math
from dataclasses import fields, is_dataclass
from functools import cache
from types import UnionType
from typing import NoReturn, TypeAliasType, Union, get_args, get_origin, get_type_hints


class ValueDecodeError(ValueError):
    """A serialized value does not have its declared structure or primitive type."""


@cache
def _annotations(model: type) -> dict[str, object]:
    return get_type_hints(model)


def _decode(value: object, expected: object, location: str) -> object:
    if isinstance(expected, TypeAliasType):
        return _decode(value, expected.__value__, location)
    origin = get_origin(expected)
    arguments = get_args(expected)
    if origin in (UnionType, Union):
        for alternative in arguments:
            try:
                return _decode(value, alternative, location)
            except ValueDecodeError:
                pass
        raise ValueDecodeError(f"{location}: value does not match the declared alternatives")
    if isinstance(expected, type) and is_dataclass(expected):
        names = {field.name for field in fields(expected)}
        if not isinstance(value, dict) or set(value) != names:
            raise ValueDecodeError(f"{location}: invalid dataclass fields")
        annotations = _annotations(expected)
        return expected(
            **{
                name: _decode(value[name], annotations[name], f"{location}.{name}")
                for name in names
            }
        )
    if origin is tuple and len(arguments) == 2 and arguments[1] is Ellipsis:
        if not isinstance(value, (list, tuple)):
            raise ValueDecodeError(f"{location}: expected an array")
        return tuple(
            _decode(item, arguments[0], f"{location}[{index}]") for index, item in enumerate(value)
        )
    if origin is list:
        if not isinstance(value, list):
            raise ValueDecodeError(f"{location}: expected an array")
        return [
            _decode(item, arguments[0], f"{location}[{index}]") for index, item in enumerate(value)
        ]
    if origin is dict:
        if not isinstance(value, dict):
            raise ValueDecodeError(f"{location}: expected an object")
        return {
            _decode(key, arguments[0], location): _decode(item, arguments[1], f"{location}.{key}")
            for key, item in value.items()
        }
    if expected in (str, int, float, bool, type(None)) and type(value) is expected:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueDecodeError(f"{location}: non-finite JSON number")
        return value
    raise ValueDecodeError(f"{location}: invalid declared value type")


def dataclass_from_mapping[T](model: type[T], value: object) -> T:
    """Decode exact fields without coercion or constructor-default substitution."""
    if not is_dataclass(model):
        raise ValueDecodeError("wire model must be a dataclass")
    result = _decode(value, model, "$")
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
