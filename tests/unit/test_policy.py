from unittest.mock import patch

import pytest

from auditwheel.policy import get_arch_name, get_policy_name, get_priority_by_name


@patch("auditwheel.policy._platform_module.machine")
@pytest.mark.parametrize("arch", [
    "armv6l",
    "armv7l",
    "ppc64le",
    "x86_64",
])
def test_arch_name(machine_mock, arch):
    machine_mock.return_value = arch
    machine = get_arch_name()
    assert machine == arch


@patch("auditwheel.policy._platform_module.machine")
@patch("auditwheel.policy.bits", 32)
def test_unknown_arch_name(machine_mock):
    machine_mock.return_value = "mipsel"
    machine = get_arch_name()
    assert machine == "i686"


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

