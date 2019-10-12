from unittest.mock import patch

import pytest

from auditwheel.policy import get_arch_name, get_policy_name, get_priority_by_name


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


class TestPolicyAccess:

    def test_get_by_priority(self):
        assert get_policy_name(100) == 'manylinux1_x86_64'
        assert get_policy_name(0) == 'linux_x86_64'

    def test_get_by_priority_missing(self):
        assert get_policy_name(101) is None

    def test_get_by_name(self):
        assert get_priority_by_name("manylinux1_x86_64") == 100

    def test_get_by_name_missing(self):
        assert get_priority_by_name("nosuchpolicy") is None

