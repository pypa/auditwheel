from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from auditwheel.error import InvalidLibc
from auditwheel.musllinux import find_musl_libc, get_musl_version


@patch("auditwheel.musllinux.pathlib.Path")
def test_find_musllinux_not_found(path_mock):
    path_mock.return_value.glob.return_value = []
    with pytest.raises(InvalidLibc):
        find_musl_libc()


@patch("auditwheel.musllinux.pathlib.Path")
def test_find_musllinux_found(path_mock):
    path_mock.return_value.glob.return_value = ["/lib/ld-musl-x86_64.so.1"]
    musl = find_musl_libc()
    assert str(musl) == "/lib/ld-musl-x86_64.so.1"


def test_get_musl_version_invalid_path():
    with pytest.raises(InvalidLibc):
        get_musl_version(Path("/tmp/no/executable/here"))


@patch("auditwheel.musllinux.subprocess.run")
def test_get_musl_version_invalid_version(run_mock):
    run_mock.return_value = subprocess.CompletedProcess([], 1, None, "Version 1.1")
    with pytest.raises(InvalidLibc):
        get_musl_version(Path("anything"))


@patch("auditwheel.musllinux.subprocess.run")
def test_get_musl_version_valid_version(run_mock):
    run_mock.return_value = subprocess.CompletedProcess([], 1, None, "Version 5.6.7")
    version = get_musl_version(Path("anything"))
    assert version.major == 5
    assert version.minor == 6
    assert version.patch == 7
