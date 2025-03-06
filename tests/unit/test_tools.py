from __future__ import annotations

import argparse
import lzma
import zipfile
import zlib
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
def test_environment_action(
    monkeypatch: pytest.MonkeyPatch,
    environ: str | None,
    passed: str | None,
    expected: str,
) -> None:
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
    assert expected == args.PLAT


def test_environment_action_invalid_plat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    choices = ["linux", "manylinux1", "manylinux2010"]
    monkeypatch.setenv("AUDITWHEEL_PLAT", "foo")
    p = argparse.ArgumentParser()
    with pytest.raises(argparse.ArgumentError):
        p.add_argument(
            "--plat",
            action=EnvironmentDefault,
            env="AUDITWHEEL_PLAT",
            dest="PLAT",
            choices=choices,
            default="manylinux1",
        )


def test_environment_action_invalid_zip_env(monkeypatch: pytest.MonkeyPatch) -> None:
    choices = list(range(zlib.Z_NO_COMPRESSION, zlib.Z_BEST_COMPRESSION + 1))
    monkeypatch.setenv("AUDITWHEEL_ZIP_LEVEL", "foo")
    p = argparse.ArgumentParser()
    with pytest.raises(argparse.ArgumentError):
        p.add_argument(
            "-z",
            "--zip-level",
            action=EnvironmentDefault,
            metavar="zip",
            env="AUDITWHEEL_ZIP_LEVEL",
            dest="zip",
            type=int,
            help="Compress level to be used to create zip file.",
            choices=choices,
            default=zlib.Z_DEFAULT_COMPRESSION,
        )
    monkeypatch.setenv("AUDITWHEEL_ZIP_LEVEL", "10")
    with pytest.raises(argparse.ArgumentError):
        p.add_argument(
            "-z",
            "--zip-level",
            action=EnvironmentDefault,
            metavar="zip",
            env="AUDITWHEEL_ZIP_LEVEL",
            dest="zip",
            type=int,
            help="Compress level to be used to create zip file.",
            choices=choices,
            default=zlib.Z_DEFAULT_COMPRESSION,
        )


def _write_test_permissions_zip(path: Path) -> None:
    source_zip_xz = Path(__file__).parent / "test-permissions.zip.xz"
    with lzma.open(source_zip_xz) as f:
        path.write_bytes(f.read())


def _check_permissions(path: Path) -> None:
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


def test_zip2dir_permissions(tmp_path: Path) -> None:
    source_zip = tmp_path / "test-permissions.zip"
    _write_test_permissions_zip(source_zip)
    extract_path = tmp_path / "unzip"
    zip2dir(source_zip, extract_path)
    _check_permissions(extract_path)


def test_zip2dir_round_trip_permissions(tmp_path: Path) -> None:
    source_zip = tmp_path / "test-permissions.zip"
    _write_test_permissions_zip(source_zip)
    extract_path = tmp_path / "unzip2"
    zip2dir(source_zip, tmp_path / "unzip1")
    dir2zip(tmp_path / "unzip1", tmp_path / "tmp.zip")
    zip2dir(tmp_path / "tmp.zip", extract_path)
    _check_permissions(extract_path)


def test_dir2zip_deflate(tmp_path: Path) -> None:
    buffer = b"\0" * 1024 * 1024
    input_dir = tmp_path / "input_dir"
    input_dir.mkdir()
    input_file = input_dir / "zeros.bin"
    input_file.write_bytes(buffer)
    output_file = tmp_path / "ouput.zip"
    dir2zip(input_dir, output_file)
    assert output_file.stat().st_size < len(buffer) / 4


def test_dir2zip_folders(tmp_path: Path) -> None:
    input_dir = tmp_path / "input_dir"
    input_dir.mkdir()
    dist_info_folder = input_dir / "dummy-1.0.dist-info"
    dist_info_folder.mkdir()
    dist_info_folder.joinpath("METADATA").write_text("")
    empty_folder = input_dir / "dummy" / "empty"
    empty_folder.mkdir(parents=True)
    output_file = tmp_path / "output.zip"
    dir2zip(input_dir, output_file)
    expected_dirs = {"dummy/", "dummy/empty/", "dummy-1.0.dist-info/"}
    with zipfile.ZipFile(output_file, "r") as z:
        assert len(z.filelist) == 4
        for info in z.filelist:
            if info.is_dir():
                assert info.filename in expected_dirs
                expected_dirs.remove(info.filename)
            else:
                assert info.filename == "dummy-1.0.dist-info/METADATA"
    assert len(expected_dirs) == 0
