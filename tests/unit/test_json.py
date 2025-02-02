from dataclasses import dataclass
from enum import Enum
from json import loads

import pytest

from auditwheel.json import dumps


def test_dataclass():

    @dataclass(frozen=True)
    class Dummy:
        first: str = "val0"
        second: int = 2

    assert {"first": "val0", "second": 2} == loads(dumps(Dummy()))


def test_enum():

    class Dummy(Enum):
        value: str

        TEST = "dummy"

        def __repr__(self):
            return self.value

    assert Dummy.TEST.value == loads(dumps(Dummy.TEST))


def test_frozenset():
    obj = frozenset((3, 9, 6, 5, 21))
    data = loads(dumps(obj))
    assert data == sorted(obj)


def test_invalid_type():

    class Dummy:
        pass
    with pytest.raises(TypeError):
        dumps(Dummy())
