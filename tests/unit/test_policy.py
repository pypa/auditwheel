from unittest.mock import patch

import pytest

from auditwheel.policy import get_arch_name, get_policy_name, \
    get_priority_by_name, get_replace_platforms, _validate_pep600_compliance


@patch("auditwheel.policy._platform_module.machine")
@patch("auditwheel.policy.bits", 32)
@pytest.mark.parametrize("reported_arch,expected_arch", [
    ("armv6l", "armv6l"),
    ("armv7l", "armv7l"),
    ("i686", "i686"),
    ("x86_64", "i686"),
])
def test_32bits_arch_name(machine_mock, reported_arch, expected_arch):
    machine_mock.return_value = reported_arch
    machine = get_arch_name()
    assert machine == expected_arch


@patch("auditwheel.policy._platform_module.machine")
@patch("auditwheel.policy.bits", 64)
@pytest.mark.parametrize("reported_arch,expected_arch", [
    ("aarch64", "aarch64"),
    ("ppc64le", "ppc64le"),
    ("x86_64", "x86_64"),
])
def test_64bits_arch_name(machine_mock, reported_arch, expected_arch):
    machine_mock.return_value = reported_arch
    machine = get_arch_name()
    assert machine == expected_arch


@pytest.mark.parametrize("name,expected", [
    ("linux_aarch64", []),
    ("manylinux1_ppc64le", ["linux_ppc64le"]),
    ("manylinux2014_x86_64", ["linux_x86_64"]),
    ("manylinux_2_24_x86_64", ["linux_x86_64"]),
])
def test_replacement_platform(name, expected):
    assert get_replace_platforms(name) == expected


def test_pep600_compliance():
    _validate_pep600_compliance([{
        "name": "manylinux1", "priority": 100, "symbol_versions": {
            "i686": {"CXXABI": ["1.3"]},
        },
        "lib_whitelist": ["libgcc_s.so.1"]
    }, {
        "name": "manylinux2010", "priority": 90, "symbol_versions": {
            "i686": {"CXXABI": ["1.3", "1.3.1"]},
        },
        "lib_whitelist": ["libgcc_s.so.1", "libstdc++.so.6"],
    }])

    _validate_pep600_compliance([{
        "name": "manylinux1", "priority": 100, "symbol_versions": {
            "i686": {"CXXABI": ["1.3"]},
            "x86_64": {"CXXABI": ["1.3"]},
        },
        "lib_whitelist": ["libgcc_s.so.1"]
    }, {
        "name": "manylinux2010", "priority": 90, "symbol_versions": {
            "i686": {"CXXABI": ["1.3", "1.3.1"]},
        },
        "lib_whitelist": ["libgcc_s.so.1", "libstdc++.so.6"],
    }])

    with pytest.raises(ValueError, match=r"manylinux2010_i686.*CXXABI.*1.3.2"):
        _validate_pep600_compliance([{
            "name": "manylinux1", "priority": 100, "symbol_versions": {
                "i686": {"CXXABI": ["1.3", "1.3.2"]},
            },
            "lib_whitelist": ["libgcc_s.so.1"]
        }, {
            "name": "manylinux2010", "priority": 90, "symbol_versions": {
                "i686": {"CXXABI": ["1.3", "1.3.1"]},
            },
            "lib_whitelist": ["libgcc_s.so.1", "libstdc++.so.6"],
        }])

    with pytest.raises(ValueError, match=r"manylinux2010.*libstdc\+\+\.so\.6"):
        _validate_pep600_compliance([{
            "name": "manylinux1", "priority": 100, "symbol_versions": {
                "i686": {"CXXABI": ["1.3"]},
            },
            "lib_whitelist": ["libgcc_s.so.1", "libstdc++.so.6"]
        }, {
            "name": "manylinux2010", "priority": 90, "symbol_versions": {
                "i686": {"CXXABI": ["1.3", "1.3.1"]},
            },
            "lib_whitelist": ["libgcc_s.so.1"],
        }])


class TestPolicyAccess:

    def test_get_by_priority(self):
        _arch = get_arch_name()
        assert get_policy_name(65) == f'manylinux_2_27_{_arch}'
        assert get_policy_name(70) == f'manylinux_2_24_{_arch}'
        assert get_policy_name(80) == f'manylinux_2_17_{_arch}'
        if _arch in {'x86_64', 'i686'}:
            assert get_policy_name(90) == f'manylinux_2_12_{_arch}'
            assert get_policy_name(100) == f'manylinux_2_5_{_arch}'
        assert get_policy_name(0) == f'linux_{_arch}'

    def test_get_by_priority_missing(self):
        assert get_policy_name(101) is None

    @patch("auditwheel.policy._POLICIES", [
        {"name": "duplicate", "priority": 0},
        {"name": "duplicate", "priority": 0},
    ])
    def test_get_by_priority_duplicate(self):
        with pytest.raises(RuntimeError):
            get_policy_name(0)

    def test_get_by_name(self):
        _arch = get_arch_name()
        assert get_priority_by_name(f"manylinux_2_27_{_arch}") == 65
        assert get_priority_by_name(f"manylinux_2_24_{_arch}") == 70
        assert get_priority_by_name(f"manylinux2014_{_arch}") == 80
        assert get_priority_by_name(f"manylinux_2_17_{_arch}") == 80
        if _arch in {'x86_64', 'i686'}:
            assert get_priority_by_name(f"manylinux2010_{_arch}") == 90
            assert get_priority_by_name(f"manylinux_2_12_{_arch}") == 90
            assert get_priority_by_name(f"manylinux1_{_arch}") == 100
            assert get_priority_by_name(f"manylinux_2_5_{_arch}") == 100

    def test_get_by_name_missing(self):
        assert get_priority_by_name("nosuchpolicy") is None

    @patch("auditwheel.policy._POLICIES", [
        {"name": "duplicate", "priority": 0},
        {"name": "duplicate", "priority": 0},
    ])
    def test_get_by_name_duplicate(self):
        with pytest.raises(RuntimeError):
            get_priority_by_name("duplicate")

