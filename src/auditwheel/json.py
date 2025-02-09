from __future__ import annotations

import dataclasses
import json
from enum import Enum
from typing import Any


def _encode_value(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, frozenset):
        return sorted(value)
    if isinstance(value, Enum):
        return repr(value)
    msg = f"object of type {value.__class__.__name__!r} can't be encoded to JSON"
    raise TypeError(msg)


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=4, default=_encode_value)
