from __future__ import annotations

import re
from contextlib import nullcontext as does_not_raise
from unittest.mock import patch

import pytest

from auditwheel.error import InvalidLibc
from auditwheel.libc import Libc
from auditwheel.policy import (
    WheelPolicies,
    _validate_pep600_compliance,
    get_arch_name,
    get_libc,
    get_replace_platforms,
)


def ids(x):
    if isinstance(x, Libc):
        return x.name
    if isinstance(x, does_not_raise):
        return "NoError"
    if hasattr(x, "expected_exception"):
        return x.expected_exception


def raises(exception, match=None, escape=True):
    if escape and match is not None:
        match = re.escape(match)
    return pytest.raises(exception, match=match)


@patch("auditwheel.policy._platform_module.machine")
@patch("auditwheel.policy.bits", 32)
@pytest.mark.parametrize(
    "reported_arch,expected_arch",
    [
        ("armv6l", "armv6l"),
        ("armv7l", "armv7l"),
        ("armv8l", "armv7l"),
        ("aarch64", "armv7l"),
        ("i686", "i686"),
        ("x86_64", "i686"),
    ],
)
def test_32bits_arch_name(machine_mock, reported_arch, expected_arch):
    machine_mock.return_value = reported_arch
    machine = get_arch_name()
    assert machine == expected_arch


@patch("auditwheel.policy._platform_module.machine")
@patch("auditwheel.policy.bits", 64)
@pytest.mark.parametrize(
    "reported_arch,expected_arch",
    [
        ("armv8l", "aarch64"),
        ("aarch64", "aarch64"),
        ("ppc64le", "ppc64le"),
        ("i686", "x86_64"),
        ("x86_64", "x86_64"),
    ],
)
def test_64bits_arch_name(machine_mock, reported_arch, expected_arch):
    machine_mock.return_value = reported_arch
    machine = get_arch_name()
    assert machine == expected_arch


@pytest.mark.parametrize(
    "name,expected",
    [
        ("linux_aarch64", []),
        ("manylinux1_ppc64le", ["linux_ppc64le"]),
        ("manylinux2014_x86_64", ["linux_x86_64"]),
        ("manylinux_2_24_x86_64", ["linux_x86_64"]),
    ],
)
def test_replacement_platform(name, expected):
    assert get_replace_platforms(name) == expected


def test_pep600_compliance():
    _validate_pep600_compliance(
        [
            {
                "name": "manylinux1",
                "priority": 100,
                "symbol_versions": {
                    "i686": {"CXXABI": ["1.3"]},
                },
                "lib_whitelist": ["libgcc_s.so.1"],
            },
            {
                "name": "manylinux2010",
                "priority": 90,
                "symbol_versions": {
                    "i686": {"CXXABI": ["1.3", "1.3.1"]},
                },
                "lib_whitelist": ["libgcc_s.so.1", "libstdc++.so.6"],
            },
        ]
    )

    _validate_pep600_compliance(
        [
            {
                "name": "manylinux1",
                "priority": 100,
                "symbol_versions": {
                    "i686": {"CXXABI": ["1.3"]},
                    "x86_64": {"CXXABI": ["1.3"]},
                },
                "lib_whitelist": ["libgcc_s.so.1"],
            },
            {
                "name": "manylinux2010",
                "priority": 90,
                "symbol_versions": {
                    "i686": {"CXXABI": ["1.3", "1.3.1"]},
                },
                "lib_whitelist": ["libgcc_s.so.1", "libstdc++.so.6"],
            },
        ]
    )

    with pytest.raises(ValueError, match=r"manylinux2010_i686.*CXXABI.*1.3.2"):
        _validate_pep600_compliance(
            [
                {
                    "name": "manylinux1",
                    "priority": 100,
                    "symbol_versions": {
                        "i686": {"CXXABI": ["1.3", "1.3.2"]},
                    },
                    "lib_whitelist": ["libgcc_s.so.1"],
                },
                {
                    "name": "manylinux2010",
                    "priority": 90,
                    "symbol_versions": {
                        "i686": {"CXXABI": ["1.3", "1.3.1"]},
                    },
                    "lib_whitelist": ["libgcc_s.so.1", "libstdc++.so.6"],
                },
            ]
        )

    with pytest.raises(ValueError, match=r"manylinux2010.*libstdc\+\+\.so\.6"):
        _validate_pep600_compliance(
            [
                {
                    "name": "manylinux1",
                    "priority": 100,
                    "symbol_versions": {
                        "i686": {"CXXABI": ["1.3"]},
                    },
                    "lib_whitelist": ["libgcc_s.so.1", "libstdc++.so.6"],
                },
                {
                    "name": "manylinux2010",
                    "priority": 90,
                    "symbol_versions": {
                        "i686": {"CXXABI": ["1.3", "1.3.1"]},
                    },
                    "lib_whitelist": ["libgcc_s.so.1"],
                },
            ]
        )


class TestPolicyAccess:
    def test_get_by_priority(self):
        _arch = get_arch_name()
        wheel_policy = WheelPolicies()
        assert wheel_policy.get_policy_name(65) == f"manylinux_2_27_{_arch}"
        assert wheel_policy.get_policy_name(70) == f"manylinux_2_24_{_arch}"
        assert wheel_policy.get_policy_name(80) == f"manylinux_2_17_{_arch}"
        if _arch in {"x86_64", "i686"}:
            assert wheel_policy.get_policy_name(90) == f"manylinux_2_12_{_arch}"
            assert wheel_policy.get_policy_name(100) == f"manylinux_2_5_{_arch}"
        assert wheel_policy.get_policy_name(0) == f"linux_{_arch}"

    def test_get_by_priority_missing(self):
        wheel_policy = WheelPolicies()
        assert wheel_policy.get_policy_name(101) is None

    def test_get_by_priority_duplicate(self):
        wheel_policy = WheelPolicies()
        wheel_policy._policies = [
            {"name": "duplicate", "priority": 0},
            {"name": "duplicate", "priority": 0},
        ]
        with pytest.raises(RuntimeError):
            wheel_policy.get_policy_name(0)

    def test_get_by_name(self):
        _arch = get_arch_name()
        wheel_policy = WheelPolicies()
        assert wheel_policy.get_priority_by_name(f"manylinux_2_27_{_arch}") == 65
        assert wheel_policy.get_priority_by_name(f"manylinux_2_24_{_arch}") == 70
        assert wheel_policy.get_priority_by_name(f"manylinux2014_{_arch}") == 80
        assert wheel_policy.get_priority_by_name(f"manylinux_2_17_{_arch}") == 80
        if _arch in {"x86_64", "i686"}:
            assert wheel_policy.get_priority_by_name(f"manylinux2010_{_arch}") == 90
            assert wheel_policy.get_priority_by_name(f"manylinux_2_12_{_arch}") == 90
            assert wheel_policy.get_priority_by_name(f"manylinux1_{_arch}") == 100
            assert wheel_policy.get_priority_by_name(f"manylinux_2_5_{_arch}") == 100

    def test_get_by_name_missing(self):
        wheel_policy = WheelPolicies()
        assert wheel_policy.get_priority_by_name("nosuchpolicy") is None

    def test_get_by_name_duplicate(self):
        wheel_policy = WheelPolicies()
        wheel_policy._policies = [
            {"name": "duplicate", "priority": 0},
            {"name": "duplicate", "priority": 0},
        ]
        with pytest.raises(RuntimeError):
            wheel_policy.get_priority_by_name("duplicate")


class TestLddTreeExternalReferences:
    """Tests for lddtree_external_references."""

    def test_filter_libs(self):
        """Test the nested filter_libs function."""
        filtered_libs = [
            "ld-linux-x86_64.so.1",
            "ld64.so.1",
            "ld64.so.2",
            "libpython3.7m.so.1.0",
            "libpython3.9.so.1.0",
            "libpython3.10.so.1.0",
            "libpython999.999.so.1.0",
        ]
        unfiltered_libs = ["libfoo.so.1.0", "libbar.so.999.999.999"]
        libs = filtered_libs + unfiltered_libs

        lddtree = {
            "realpath": "/path/to/lib",
            "needed": libs,
            "libs": {lib: {"needed": [], "realpath": "/path/to/lib"} for lib in libs},
        }
        wheel_policy = WheelPolicies()
        full_external_refs = wheel_policy.lddtree_external_references(
            lddtree, "/path/to/wheel"
        )

        # Assert that each policy only has the unfiltered libs.
        for policy in full_external_refs:
            assert set(full_external_refs[policy]["libs"]) == set(unfiltered_libs)


@pytest.mark.parametrize(
    "libc,musl_policy,arch,exception",
    [
        # valid
        (None, None, None, does_not_raise()),
        (Libc.GLIBC, None, None, does_not_raise()),
        (Libc.MUSL, "musllinux_1_1", None, does_not_raise()),
        (None, "musllinux_1_1", None, does_not_raise()),
        (None, None, "aarch64", does_not_raise()),
        # invalid
        (
            Libc.GLIBC,
            "musllinux_1_1",
            None,
            raises(ValueError, "'musl_policy' shall be None"),
        ),
        (Libc.MUSL, "manylinux_1_1", None, raises(ValueError, "Invalid 'musl_policy'")),
        (Libc.MUSL, "musllinux_5_1", None, raises(AssertionError)),
        (Libc.MUSL, "musllinux_1_1", "foo", raises(AssertionError)),
        # platform dependant
        (
            Libc.MUSL,
            None,
            None,
            does_not_raise() if get_libc() == Libc.MUSL else raises(InvalidLibc),
        ),
    ],
    ids=ids,
)
def test_wheel_policies_args(libc, musl_policy, arch, exception):
    with exception:
        wheel_policies = WheelPolicies(libc=libc, musl_policy=musl_policy, arch=arch)
        if libc is not None:
            assert wheel_policies._libc_variant == libc
        if musl_policy is not None:
            assert wheel_policies._musl_policy == musl_policy
        if arch is not None:
            assert wheel_policies._arch_name == arch
