from __future__ import annotations

import dataclasses
import json
from enum import Enum
from pathlib import PurePath
from typing import Any


class _CustomEncoder(json.JSONEncoder):
    def default(self, value: Any) -> Any:  # noqa: ANN401
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            as_dict = dataclasses.asdict(value)
            as_dict.pop("policy", None)  # don't dump full policy in logs
            return as_dict
        if isinstance(value, frozenset):
            return sorted(value)
        if isinstance(value, Enum):
            return repr(value)
        if isinstance(value, PurePath):
            return str(value)
        return super().default(value)

    def encode(self, o: Any) -> str:  # noqa: ANN401
        if isinstance(o, dict):
            o = {str(k): v for k, v in o.items()}
        return super().encode(o)


def dumps(obj: Any) -> str:  # noqa: ANN401
    return json.dumps(obj, indent=4, cls=_CustomEncoder)
