from unittest.mock import patch

import pytest

from auditwheel.policy import get_arch_name, get_policy_name, get_priority_by_name

TEST_POLICIES = [
    {'name': 'linux_x86_64', 'priority': 0, 'symbol_versions': {}, 'lib_whitelist': []},
    {'name': 'manylinux1_x86_64', 'priority': 100, 'symbol_versions':
        {'GLIBC': ['2.0', '2.1', '2.1.1', '2.1.2', '2.1.3', '2.2', '2.2.1', '2.2.2',
                   '2.2.3', '2.2.4', '2.2.5', '2.2.6', '2.3', '2.3.2', '2.3.3', '2.3.4',
                   '2.4', '2.5'], 'CXXABI': ['1.3', '1.3.1'],
         'GLIBCXX': ['3.4', '3.4.1', '3.4.2', '3.4.3', '3.4.4', '3.4.5', '3.4.6', '3.4.7',
                     '3.4.8'],
         'GCC': ['3.0', '3.3', '3.3.1', '3.4', '3.4.2', '3.4.4', '4.0.0', '4.2.0']},
     'lib_whitelist': ['libpanelw.so.5', 'libncursesw.so.5', 'libgcc_s.so.1',
                       'libstdc++.so.6', 'libm.so.6', 'libdl.so.2', 'librt.so.1',
                       'libcrypt.so.1', 'libc.so.6', 'libnsl.so.1', 'libutil.so.1',
                       'libpthread.so.0', 'libX11.so.6', 'libXext.so.6',
                       'libXrender.so.1', 'libICE.so.6', 'libSM.so.6', 'libGL.so.1',
                       'libgobject-2.0.so.0', 'libgthread-2.0.so.0', 'libglib-2.0.so.0',
                       'libresolv.so.2']},
    {'name': 'manylinux2010_x86_64', 'priority': 90, 'symbol_versions': {
        'GLIBC': ['2.2.5', '2.2.6', '2.3', '2.3.2', '2.3.3', '2.3.4', '2.4', '2.5', '2.6',
                  '2.7', '2.8', '2.9', '2.10', '2.11', '2.12'],
        'CXXABI': ['1.3', '1.3.1', '1.3.2', '1.3.3'],
        'GLIBCXX': ['3.4', '3.4.1', '3.4.2', '3.4.3', '3.4.4', '3.4.5', '3.4.6', '3.4.7',
                    '3.4.8', '3.4.9', '3.4.10', '3.4.11', '3.4.12', '3.4.13'],
        'GCC': ['3.0', '3.3', '3.3.1', '3.4', '3.4.2', '3.4.4', '4.0.0', '4.2.0',
                '4.3.0']},
     'lib_whitelist': ['libgcc_s.so.1', 'libstdc++.so.6', 'libm.so.6', 'libdl.so.2',
                       'librt.so.1', 'libcrypt.so.1', 'libc.so.6', 'libnsl.so.1',
                       'libutil.so.1', 'libpthread.so.0', 'libX11.so.6', 'libXext.so.6',
                       'libXrender.so.1', 'libICE.so.6', 'libSM.so.6', 'libGL.so.1',
                       'libgobject-2.0.so.0', 'libgthread-2.0.so.0', 'libglib-2.0.so.0',
                       'libresolv.so.2']}]


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

    @patch("auditwheel.policy._POLICIES", TEST_POLICIES)
    def test_get_by_priority(self):
        assert get_policy_name(100) == 'manylinux1_x86_64'
        assert get_policy_name(0) == 'linux_x86_64'

    @patch("auditwheel.policy._POLICIES", TEST_POLICIES)
    def test_get_by_priority_missing(self):
        assert get_policy_name(101) is None

    @patch("auditwheel.policy._POLICIES", TEST_POLICIES * 2)
    def test_get_by_priority_duplicates(self):
        """Duplicate priorities raise RuntimeError"""
        with pytest.raises(RuntimeError):
            get_policy_name(0)

    @patch("auditwheel.policy._POLICIES", TEST_POLICIES)
    def test_get_by_name(self):
        assert get_priority_by_name("manylinux1_x86_64") == 100

    @patch("auditwheel.policy._POLICIES", TEST_POLICIES)
    def test_get_by_name_missing(self):
        assert get_priority_by_name("nosuchpolicy") is None

    @patch("auditwheel.policy._POLICIES", TEST_POLICIES * 2)
    def test_get_by_name_duplicate(self):
        """Duplicate priorities raise RuntimeError"""
        with pytest.raises(RuntimeError):
            get_policy_name(0)
