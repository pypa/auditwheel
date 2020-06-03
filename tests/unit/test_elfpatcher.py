from subprocess import CalledProcessError
from unittest.mock import patch, call

import pytest

from auditwheel.patcher import Patchelf


@patch("auditwheel.patcher.find_executable")
def test_patchelf_unavailable(find_executable):
    find_executable.return_value = False
    with pytest.raises(ValueError):
        Patchelf()


@patch("auditwheel.patcher.check_output")
def test_patchelf_check_output_fail(check_output):
    check_output.side_effect = CalledProcessError(1, "patchelf --version")
    with pytest.raises(ValueError, match="Could not call"):
        Patchelf()


@patch("auditwheel.patcher.check_output")
@pytest.mark.parametrize("version", ["0.9", "0.9.1", "0.10"])
def test_patchelf_version_check(check_output, version):
    check_output.return_value.decode.return_value = "patchelf {}".format(version)
    Patchelf()


@patch("auditwheel.patcher.check_output")
@pytest.mark.parametrize("version", ["0.8", "0.8.1", "0.1"])
def test_patchelf_version_check_fail(check_output, version):
    check_output.return_value.decode.return_value = "patchelf {}".format(version)
    with pytest.raises(ValueError, match="patchelf {} found".format(version)):
        Patchelf()


@patch("auditwheel.patcher._verify_patchelf")
@patch("auditwheel.patcher.check_call")
class TestPatchElf:
    """"Validate that patchelf is invoked with the correct arguments."""

    def test_replace_needed(self, check_call, _):
        patcher = Patchelf()
        filename = "test.so"
        soname_old = "TEST_OLD"
        soname_new = "TEST_NEW"
        patcher.replace_needed(filename, soname_old, soname_new)
        check_call.assert_called_once_with(['patchelf', '--replace-needed',
                                            soname_old, soname_new, filename])

    def test_set_soname(self, check_call, _):
        patcher = Patchelf()
        filename = "test.so"
        soname_new = "TEST_NEW"
        patcher.set_soname(filename, soname_new)
        check_call.assert_called_once_with(['patchelf', '--set-soname',
                                            soname_new, filename])

    def test_set_rpath(self, check_call, _):
        patcher = Patchelf()
        patcher.set_rpath("test.so", "$ORIGIN/.lib")
        expected_args = [call(['patchelf', '--print-rpath', 'test.so']),
                         call(['patchelf', '--remove-rpath', 'test.so']),
                         call(['patchelf', '--force-rpath', '--set-rpath',
                               '$ORIGIN/.lib', 'test.so'])]

        assert check_call.call_args_list == expected_args

    def test_set_additional_rpath(self, check_call, _):
        patcher = Patchelf()
        patcher.set_rpath("test.so", "$ORIGIN/.existinglibdir")
        patcher.set_rpath("test.so", "$ORIGIN/.lib")
        expected_args = [call(['patchelf', '--print-rpath', 'test.so']),
                         call(['patchelf', '--remove-rpath', 'test.so']),
                         call(['patchelf', '--force-rpath', '--set-rpath',
                               '$ORIGIN/.existinglibdir', 'test.so']),
                         call(['patchelf', '--print-rpath', 'test.so']),
                         call(['patchelf', '--remove-rpath', 'test.so']),
                         call(['patchelf', '--force-rpath', '--set-rpath',
                               '$ORIGIN/.existinglibdir:$ORIGIN/.lib',
                               'test.so'])]

        assert check_call.call_args_list == expected_args
