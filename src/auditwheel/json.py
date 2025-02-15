from __future__ import annotations

import dataclasses
import json
from enum import Enum
from typing import Any


def _encode_value(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        as_dict = dataclasses.asdict(value)
        as_dict.pop("policy", None)  # don't dump full policy in logs
        return as_dict
    if isinstance(value, frozenset):
        return sorted(value)
    if isinstance(value, Enum):
        return repr(value)
    msg = f"object of type {value.__class__.__name__!r} can't be encoded to JSON"
    raise TypeError(msg)


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=4, default=_encode_value)
