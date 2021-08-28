import subprocess
from unittest.mock import patch

import pytest

from auditwheel.error import InvalidLibc
from auditwheel.musllinux import find_musl_libc, get_musl_version


@patch("auditwheel.musllinux.subprocess.check_output")
def test_find_musllinux_no_ldd(check_output_mock):
    check_output_mock.side_effect = FileNotFoundError()
    with pytest.raises(InvalidLibc):
        find_musl_libc()


@patch("auditwheel.musllinux.subprocess.check_output")
def test_find_musllinux_ldd_error(check_output_mock):
    check_output_mock.side_effect = subprocess.CalledProcessError(1, "ldd")
    with pytest.raises(InvalidLibc):
        find_musl_libc()


@patch("auditwheel.musllinux.subprocess.check_output")
def test_find_musllinux_not_found(check_output_mock):
    check_output_mock.return_value = ""
    with pytest.raises(InvalidLibc):
        find_musl_libc()


def test_get_musl_version_invalid_path():
    with pytest.raises(InvalidLibc):
        get_musl_version("/tmp/no/executable/here")


@patch("auditwheel.musllinux.subprocess.run")
def test_get_musl_version_invalid_version(run_mock):
    run_mock.return_value = subprocess.CompletedProcess([], 1, None, "Version 1.1")
    with pytest.raises(InvalidLibc):
        get_musl_version("anything")


@patch("auditwheel.musllinux.subprocess.run")
def test_get_musl_version_valid_version(run_mock):
    run_mock.return_value = subprocess.CompletedProcess([], 1, None, "Version 5.6.7")
    version = get_musl_version("anything")
    assert version.major == 5
    assert version.minor == 6
    assert version.patch == 7
