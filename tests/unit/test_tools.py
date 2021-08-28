import argparse
import lzma
from pathlib import Path

import pytest

from auditwheel.tools import EnvironmentDefault, dir2zip, zip2dir


@pytest.mark.parametrize(
    ("environ", "passed", "expected"),
    [
        (None, None, "manylinux1"),
        (None, "manylinux2010", "manylinux2010"),
        ("manylinux2010", None, "manylinux2010"),
        ("manylinux2010", "linux", "linux"),
    ],
)
def test_environment_action(monkeypatch, environ, passed, expected):
    choices = ["linux", "manylinux1", "manylinux2010"]
    argv = []
    if passed:
        argv = ["--plat", passed]
    if environ:
        monkeypatch.setenv("AUDITWHEEL_PLAT", environ)
    p = argparse.ArgumentParser()
    p.add_argument(
        "--plat",
        action=EnvironmentDefault,
        env="AUDITWHEEL_PLAT",
        dest="PLAT",
        choices=choices,
        default="manylinux1",
    )
    args = p.parse_args(argv)
    assert args.PLAT == expected


def test_environment_action_invalid_env(monkeypatch):
    choices = ["linux", "manylinux1", "manylinux2010"]
    monkeypatch.setenv("AUDITWHEEL_PLAT", "foo")
    with pytest.raises(argparse.ArgumentError):
        p = argparse.ArgumentParser()
        p.add_argument(
            "--plat",
            action=EnvironmentDefault,
            env="AUDITWHEEL_PLAT",
            dest="PLAT",
            choices=choices,
            default="manylinux1",
        )


def _write_test_permissions_zip(path):
    source_zip_xz = Path(__file__).parent / "test-permissions.zip.xz"
    with lzma.open(source_zip_xz) as f:
        path.write_bytes(f.read())


def _check_permissions(path):
    for i in range(8):
        for j in range(8):
            for k in range(8):
                mode = (path / f"{i}{j}{k}.f").stat().st_mode
                assert ((mode >> 6) & 7) == (i | 6)  # always read/write
                assert ((mode >> 3) & 7) == j
                assert ((mode >> 0) & 7) == k
                mode = (path / f"{i}{j}{k}.d").stat().st_mode
                assert ((mode >> 6) & 7) == 7  # always read/write/execute
                assert ((mode >> 3) & 7) == 5  # always read/execute
                assert ((mode >> 0) & 7) == 5  # always read/execute


def test_zip2dir_permissions(tmp_path):
    source_zip = tmp_path / "test-permissions.zip"
    _write_test_permissions_zip(source_zip)
    extract_path = tmp_path / "unzip"
    zip2dir(str(source_zip), str(extract_path))
    _check_permissions(extract_path)


def test_zip2dir_round_trip_permissions(tmp_path):
    source_zip = tmp_path / "test-permissions.zip"
    _write_test_permissions_zip(source_zip)
    extract_path = tmp_path / "unzip2"
    zip2dir(str(source_zip), str(tmp_path / "unzip1"))
    dir2zip(str(tmp_path / "unzip1"), str(tmp_path / "tmp.zip"))
    zip2dir(str(tmp_path / "tmp.zip"), str(extract_path))
    _check_permissions(extract_path)
