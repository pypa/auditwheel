from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

from auditwheel.musllinux import find_musl_libc, get_musl_version


@patch("auditwheel.musllinux.pathlib.Path")
def test_find_musllinux_not_found(path_mock):
    path_mock.return_value.glob.return_value = []
    assert find_musl_libc() is None


@patch("auditwheel.musllinux.pathlib.Path")
def test_find_musllinux_found(path_mock):
    path_mock.return_value.glob.return_value = ["/lib/ld-musl-x86_64.so.1"]
    musl = find_musl_libc()
    assert musl


def test_get_musl_version_invalid_path():
    assert get_musl_version("/tmp/no/executable/here") is None


@patch("auditwheel.musllinux.open")
def test_get_musl_version_invalid_version(run_mock):
    run_mock.return_value = BytesIO(b"jklasdfjkl Version 1.1")
    assert get_musl_version("anything") is None


@patch("auditwheel.musllinux.open")
def test_get_musl_version_valid_version(run_mock):
    run_mock.return_value = BytesIO(b"jklasdfjkl Version 5.6.7\0 sjlkdfjkl")
    version = get_musl_version("anything")
    assert version.major == 5
    assert version.minor == 6
    assert version.patch == 7
