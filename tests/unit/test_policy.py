from __future__ import annotations

import re
from contextlib import nullcontext as does_not_raise
from pathlib import Path

import pytest

from auditwheel.architecture import Architecture
from auditwheel.lddtree import DynamicExecutable, DynamicLibrary, Platform
from auditwheel.libc import Libc
from auditwheel.policy import (
    Policy,
    WheelPolicies,
    _validate_pep600_compliance,
    get_replace_platforms,
)


def ids(x):
    if isinstance(x, Libc):
        return x.name
    if isinstance(x, does_not_raise):
        return "NoError"
    if hasattr(x, "expected_exception"):
        return x.expected_exception
    return None


def raises(exception, match=None, escape=True):
    if escape and match is not None:
        match = re.escape(match)
    return pytest.raises(exception, match=match)


@pytest.mark.parametrize(
    ("name", "expected"),
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
    def test_get_by_name(self):
        arch = Architecture.detect()
        policies = WheelPolicies(libc=Libc.GLIBC, arch=arch)
        assert policies.get_policy_by_name(f"manylinux_2_27_{arch}").priority == 65
        assert policies.get_policy_by_name(f"manylinux_2_24_{arch}").priority == 70
        assert policies.get_policy_by_name(f"manylinux2014_{arch}").priority == 80
        assert policies.get_policy_by_name(f"manylinux_2_17_{arch}").priority == 80
        if arch not in {Architecture.x86_64, Architecture.i686}:
            return
        assert policies.get_policy_by_name(f"manylinux2010_{arch}").priority == 90
        assert policies.get_policy_by_name(f"manylinux_2_12_{arch}").priority == 90
        assert policies.get_policy_by_name(f"manylinux1_{arch}").priority == 100
        assert policies.get_policy_by_name(f"manylinux_2_5_{arch}").priority == 100

    def test_get_by_name_missing(self):
        policies = WheelPolicies(libc=Libc.GLIBC, arch=Architecture.x86_64)
        with pytest.raises(LookupError):
            policies.get_policy_by_name("nosuchpolicy")

    def test_get_by_name_duplicate(self):
        policies = WheelPolicies(libc=Libc.GLIBC, arch=Architecture.x86_64)
        policy = Policy("duplicate", (), 0, {}, frozenset(), {})
        policies._policies = [policy, policy]
        with pytest.raises(RuntimeError):
            policies.get_policy_by_name("duplicate")


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
        lddtree = DynamicExecutable(
            interpreter=None,
            libc=Libc.GLIBC,
            path="/path/to/lib",
            realpath=Path("/path/to/lib"),
            platform=Platform(
                "", 64, True, "EM_X86_64", Architecture.x86_64, None, None
            ),
            needed=tuple(libs),
            libraries={
                lib: DynamicLibrary(lib, f"/path/to/{lib}", Path(f"/path/to/{lib}"))
                for lib in libs
            },
            rpath=(),
            runpath=(),
        )
        policies = WheelPolicies(libc=Libc.GLIBC, arch=Architecture.x86_64)
        full_external_refs = policies.lddtree_external_references(
            lddtree, Path("/path/to/wheel")
        )

        # Assert that each policy only has the unfiltered libs.
        for policy in full_external_refs:
            if policy.startswith("linux_"):
                assert set(full_external_refs[policy].libs) == set()
            else:
                assert set(full_external_refs[policy].libs) == set(unfiltered_libs)


@pytest.mark.parametrize(
    ("libc", "musl_policy", "arch", "exception"),
    [
        # valid
        (Libc.detect(), None, Architecture.detect(), does_not_raise()),
        (Libc.GLIBC, None, Architecture.x86_64, does_not_raise()),
        (Libc.MUSL, "musllinux_1_1", Architecture.x86_64, does_not_raise()),
        (Libc.GLIBC, None, Architecture.aarch64, does_not_raise()),
        # invalid
        (
            Libc.GLIBC,
            "musllinux_1_1",
            Architecture.x86_64,
            raises(ValueError, "'musl_policy' shall be None"),
        ),
        (
            Libc.MUSL,
            "manylinux_1_1",
            Architecture.x86_64,
            raises(ValueError, "Invalid 'musl_policy'"),
        ),
        (Libc.MUSL, "musllinux_5_1", Architecture.x86_64, raises(AssertionError)),
        (Libc.MUSL, None, Architecture.x86_64, does_not_raise()),
    ],
    ids=ids,
)
def test_wheel_policies_args(libc, musl_policy, arch, exception):
    with exception:
        policies = WheelPolicies(libc=libc, musl_policy=musl_policy, arch=arch)
        assert policies.libc == libc
        assert policies.architecture == arch
        if musl_policy is not None:
            assert policies._musl_policy == musl_policy
        elif libc == Libc.MUSL:
            assert policies._musl_policy == "musllinux_1_2"


def test_policy_checks_glibc():
    policies = WheelPolicies(libc=Libc.GLIBC, arch=Architecture.x86_64)

    policy = policies.versioned_symbols_policy({"some_library.so": {"GLIBC_2.17"}})
    assert policy > policies.linux
    policy = policies.versioned_symbols_policy({"some_library.so": {"GLIBC_999"}})
    assert policy == policies.linux
    policy = policies.versioned_symbols_policy({"some_library.so": {"OPENSSL_1_1_0"}})
    assert policy == policies.highest
    policy = policies.versioned_symbols_policy({"some_library.so": {"IAMALIBRARY"}})
    assert policy == policies.highest
    assert policies.linux < policies.lowest < policies.highest
