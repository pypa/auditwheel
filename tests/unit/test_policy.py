from unittest.mock import patch

import pytest

from auditwheel.policy import get_arch_name, get_policy_name, \
    get_priority_by_name, get_replace_platforms


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
])
def test_replacement_platform(name, expected):
    assert get_replace_platforms(name) == expected


class TestPolicyAccess:

    def test_get_by_priority(self):
        _arch = get_arch_name()
        assert get_policy_name(80) == f'manylinux2014_{_arch}'
        if _arch in {'x86_64', 'i686'}:
            assert get_policy_name(90) == f'manylinux2010_{_arch}'
            assert get_policy_name(100) == f'manylinux1_{_arch}'
        assert get_policy_name(0) == f'linux_{_arch}'

    def test_get_by_priority_missing(self):
        assert get_policy_name(101) is None

    def test_get_by_name(self):
        _arch = get_arch_name()
        assert get_priority_by_name(f"manylinux2014_{_arch}") == 80
        if _arch in {'x86_64', 'i686'}:
            assert get_priority_by_name(f"manylinux2010_{_arch}") == 90
            assert get_priority_by_name(f"manylinux1_{_arch}") == 100

    def test_get_by_name_missing(self):
        assert get_priority_by_name("nosuchpolicy") is None

