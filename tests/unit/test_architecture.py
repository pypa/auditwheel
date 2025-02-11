import platform
import struct
import sys

import pytest

from auditwheel.architecture import Architecture


@pytest.mark.parametrize(
    ("sys_platform", "reported_arch", "expected_arch"),
    [
        ("linux", "armv7l", Architecture.armv7l),
        ("linux", "armv8l", Architecture.armv7l),
        ("linux", "aarch64", Architecture.armv7l),
        ("linux", "i686", Architecture.i686),
        ("linux", "x86_64", Architecture.i686),
        ("win32", "x86", Architecture.i686),
        ("win32", "AMD64", Architecture.i686),
    ],
)
def test_32bits_arch_name(sys_platform, reported_arch, expected_arch, monkeypatch):
    monkeypatch.setattr(sys, "platform", sys_platform)
    monkeypatch.setattr(platform, "machine", lambda: reported_arch)
    machine = Architecture.detect(bits=32)
    assert machine == expected_arch


@pytest.mark.parametrize(
    ("sys_platform", "reported_arch", "expected_arch"),
    [
        ("linux", "armv8l", Architecture.aarch64),
        ("linux", "aarch64", Architecture.aarch64),
        ("linux", "ppc64le", Architecture.ppc64le),
        ("linux", "i686", Architecture.x86_64),
        ("linux", "x86_64", Architecture.x86_64),
        ("darwin", "arm64", Architecture.aarch64),
        ("darwin", "x86_64", Architecture.x86_64),
        ("win32", "ARM64", Architecture.aarch64),
        ("win32", "AMD64", Architecture.x86_64),
    ],
)
def test_64bits_arch_name(sys_platform, reported_arch, expected_arch, monkeypatch):
    monkeypatch.setattr(sys, "platform", sys_platform)
    monkeypatch.setattr(platform, "machine", lambda: reported_arch)
    machine = Architecture.detect(bits=64)
    assert machine == expected_arch


@pytest.mark.parametrize(
    ("maxsize", "sizeof_voidp", "expected"),
    [
        # 64-bit
        (9223372036854775807, 8, Architecture.x86_64),
        # 32-bit
        (2147483647, 4, Architecture.i686),
        # 64-bit w/ 32-bit sys.maxsize: GraalPy, IronPython, Jython
        (2147483647, 8, Architecture.x86_64),
    ],
)
def test_arch_name_bits(maxsize, sizeof_voidp, expected, monkeypatch):
    def _calcsize(fmt):
        assert fmt == "P"
        return sizeof_voidp

    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(sys, "maxsize", maxsize)
    monkeypatch.setattr(struct, "calcsize", _calcsize)
    machine = Architecture.detect()
    assert machine == expected


@pytest.mark.parametrize(
    ("smaller", "larger"),
    [
        (Architecture.x86_64, Architecture.x86_64_v4),
        (Architecture.x86_64, Architecture.x86_64),
        (Architecture.x86_64, Architecture.x86_64_v2),
        (Architecture.x86_64_v2, Architecture.x86_64_v3),
        (Architecture.x86_64_v3, Architecture.x86_64_v4),
    ],
)
def test_order_valid(smaller, larger):
    assert smaller.is_subset(larger)
    assert larger.is_superset(smaller)


@pytest.mark.parametrize(
    ("smaller", "larger"),
    [
        (Architecture.x86_64, Architecture.x86_64_v4),
        (Architecture.x86_64, Architecture.x86_64_v2),
        (Architecture.x86_64_v2, Architecture.x86_64_v3),
        (Architecture.x86_64_v3, Architecture.x86_64_v4),
        (Architecture.aarch64, Architecture.x86_64),
        (Architecture.x86_64, Architecture.aarch64),
    ],
)
def test_order_invalid(smaller, larger):
    assert not smaller.is_superset(larger)
    assert not larger.is_subset(smaller)
