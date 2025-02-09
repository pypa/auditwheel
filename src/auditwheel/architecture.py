from __future__ import annotations

import functools
import platform
import struct
import sys
from enum import Enum


class Architecture(Enum):
    value: str

    aarch64 = "aarch64"
    armv7l = "armv7l"
    i686 = "i686"
    loongarch64 = "loongarch64"
    ppc64 = "ppc64"
    ppc64le = "ppc64le"
    riscv64 = "riscv64"
    s390x = "s390x"
    x86_64 = "x86_64"
    x86_64_v2 = "x86_64_v2"
    x86_64_v3 = "x86_64_v3"
    x86_64_v4 = "x86_64_v4"

    def __str__(self):
        return self.value

    @property
    def baseline(self):
        if self.value.startswith("x86_64"):
            return Architecture.x86_64
        return self

    @classmethod
    @functools.lru_cache(None)
    def _member_list(cls) -> list[Architecture]:
        return list(cls)

    def is_subset(self, other: Architecture) -> bool:
        if self.baseline != other.baseline:
            return False
        member_list = Architecture._member_list()
        return member_list.index(self) <= member_list.index(other)

    def is_superset(self, other: Architecture) -> bool:
        if self.baseline != other.baseline:
            return False
        return other.is_subset(self)

    @staticmethod
    def get_native_architecture(*, bits: int | None = None) -> Architecture:
        machine = platform.machine()
        if sys.platform.startswith("win"):
            machine = {"AMD64": "x86_64", "ARM64": "aarch64", "x86": "i686"}.get(
                machine, machine
            )
        elif sys.platform.startswith("darwin"):
            machine = {"arm64": "aarch64"}.get(machine, machine)

        if bits is None:
            # c.f. https://github.com/pypa/packaging/pull/711
            bits = 8 * struct.calcsize("P")

        if machine in {"x86_64", "i686"}:
            machine = {64: "x86_64", 32: "i686"}[bits]
        elif machine in {"aarch64", "armv8l"}:
            # use armv7l policy for 64-bit arm kernel in 32-bit mode (armv8l)
            machine = {64: "aarch64", 32: "armv7l"}[bits]

        return Architecture(machine)
