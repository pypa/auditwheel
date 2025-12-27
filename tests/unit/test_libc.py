from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from auditwheel.error import InvalidLibcError
from auditwheel.libc import Libc, LibcVersion, _find_musl_libc, _get_musl_version


@patch("auditwheel.libc.Path")
def test_find_musllinux_not_found(path_mock):
    path_mock.return_value.glob.return_value = []
    with pytest.raises(InvalidLibcError):
        _find_musl_libc()
    assert Libc.detect() != Libc.MUSL


@patch("auditwheel.libc.Path")
def test_find_musllinux_found(path_mock):
    path_mock.return_value.glob.return_value = ["/lib/ld-musl-dummy.so.1"]
    musl = _find_musl_libc()
    assert str(musl) == "/lib/ld-musl-dummy.so.1"
    assert Libc.detect() == Libc.MUSL


def test_get_musl_version_invalid_path():
    with pytest.raises(InvalidLibcError):
        _get_musl_version(Path("/tmp/no/executable/here"))  # noqa: S108


@patch("auditwheel.libc.subprocess.run")
def test_get_musl_version_invalid_version(run_mock):
    run_mock.return_value = subprocess.CompletedProcess([], 1, None, "Version 1.1")
    with pytest.raises(InvalidLibcError):
        _get_musl_version(Path("anything"))


@patch("auditwheel.libc.subprocess.run")
def test_get_musl_version_valid_version(run_mock):
    run_mock.return_value = subprocess.CompletedProcess([], 1, None, "Version 5.6.7")
    version = _get_musl_version(Path("anything"))
    assert version.major == 5
    assert version.minor == 6


@patch("auditwheel.libc.Path")
def test_detect_glibc(path_mock):
    path_mock.return_value.glob.return_value = []
    assert Libc.detect() == Libc.GLIBC


@pytest.mark.parametrize(
    "confstr",
    [
        "glibc 42.42",
        "glibc 42.42-test",
        "glibc 42.42.0",
        "glibc 42.42~0",
    ],
)
def test_glibc_version(monkeypatch, confstr):
    monkeypatch.setattr(os, "confstr", lambda _: confstr)
    assert Libc.GLIBC.get_current_version() == LibcVersion(42, 42)


@pytest.mark.parametrize(
    "confstr",
    [
        None,
        "glibc",
        "glibc 42.42 test",
        "glibc 42",
        "glibc 42.test",
        "glibc test.42",
    ],
)
def test_bad_glibc_version(monkeypatch, confstr):
    monkeypatch.setattr(os, "confstr", lambda _: confstr)
    with pytest.raises(InvalidLibcError):
        Libc.GLIBC.get_current_version()
