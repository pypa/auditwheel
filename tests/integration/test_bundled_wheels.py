from __future__ import annotations

import importlib
import os
import platform
import sys
import zipfile
from argparse import Namespace
from datetime import datetime, timezone
from os.path import isabs
from pathlib import Path
from unittest.mock import Mock

import pytest

from auditwheel import lddtree, main_repair
from auditwheel.architecture import Architecture
from auditwheel.libc import Libc
from auditwheel.main import main
from auditwheel.wheel_abi import NonPlatformWheel, analyze_wheel_abi

HERE = Path(__file__).parent.resolve()


@pytest.mark.parametrize(
    ("file", "external_libs", "exclude"),
    [
        (
            "cffi-1.5.0-cp27-none-linux_x86_64.whl",
            {"libffi.so.5", "libpython2.7.so.1.0"},
            frozenset(),
        ),
        (
            "cffi-1.5.0-cp27-none-linux_x86_64.whl",
            set(),
            frozenset(["libffi.so.5", "libpython2.7.so.1.0"]),
        ),
        (
            "cffi-1.5.0-cp27-none-linux_x86_64.whl",
            {"libffi.so.5", "libpython2.7.so.1.0"},
            frozenset(["libffi.so.noexist", "libnoexist.so.*"]),
        ),
        (
            "cffi-1.5.0-cp27-none-linux_x86_64.whl",
            {"libpython2.7.so.1.0"},
            frozenset(["libffi.so.[4,5]"]),
        ),
        (
            "cffi-1.5.0-cp27-none-linux_x86_64.whl",
            {"libffi.so.5", "libpython2.7.so.1.0"},
            frozenset(["libffi.so.[6,7]"]),
        ),
        (
            "cffi-1.5.0-cp27-none-linux_x86_64.whl",
            {"libpython2.7.so.1.0"},
            frozenset([f"{HERE}/*"]),
        ),
        (
            "cffi-1.5.0-cp27-none-linux_x86_64.whl",
            {"libpython2.7.so.1.0"},
            frozenset(["libffi.so.*"]),
        ),
        ("cffi-1.5.0-cp27-none-linux_x86_64.whl", set(), frozenset(["*"])),
        (
            "python_snappy-0.5.2-pp260-pypy_41-linux_x86_64.whl",
            {"libsnappy.so.1"},
            frozenset(),
        ),
    ],
)
def test_analyze_wheel_abi(file, external_libs, exclude):
    # If exclude libs contain path, LD_LIBRARY_PATH need to be modified to find the libs
    # `lddtree.load_ld_paths` needs to be reloaded for it's `lru_cache`-ed.
    modify_ld_library_path = any(isabs(e) for e in exclude)
    lddtree.parse_ld_so_conf.cache_clear()

    for env_var in ["LD_LIBRARY_PATH", "AUDITWHEEL_LD_LIBRARY_PATH"]:
        with pytest.MonkeyPatch.context() as cp:
            if modify_ld_library_path:
                cp.setenv(env_var, f"{HERE}")
                importlib.reload(lddtree)

            winfo = analyze_wheel_abi(
                Libc.GLIBC, Architecture.x86_64, HERE / file, exclude, False, True
            )
            assert (
                set(winfo.external_refs["manylinux_2_5_x86_64"].libs) == external_libs
            ), f"{HERE}, {exclude}, {os.environ}"
            lddtree.parse_ld_so_conf.cache_clear()

        if modify_ld_library_path:
            importlib.reload(lddtree)


def test_analyze_wheel_abi_pyfpe():
    winfo = analyze_wheel_abi(
        Libc.GLIBC,
        Architecture.x86_64,
        HERE / "fpewheel-0.0.0-cp35-cp35m-linux_x86_64.whl",
        frozenset(),
        False,
        True,
    )
    # for external symbols, it could get manylinux1
    assert winfo.sym_policy.name == "manylinux_2_5_x86_64"
    # but for having the pyfpe reference, it gets just linux
    assert winfo.pyfpe_policy.name == "linux_x86_64"
    assert winfo.overall_policy.name == "linux_x86_64"


def test_show_wheel_abi_pyfpe(monkeypatch, capsys):
    wheel = str(HERE / "fpewheel-0.0.0-cp35-cp35m-linux_x86_64.whl")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(sys, "argv", ["auditwheel", "show", wheel])
    assert main() == 0
    captured = capsys.readouterr()
    assert "This wheel uses the PyFPE_jbuf function" in captured.out


def test_analyze_wheel_abi_bad_architecture():
    with pytest.raises(NonPlatformWheel):
        analyze_wheel_abi(
            Libc.GLIBC,
            Architecture.aarch64,
            HERE / "fpewheel-0.0.0-cp35-cp35m-linux_x86_64.whl",
            frozenset(),
            False,
            True,
        )


def test_analyze_wheel_abi_static_exe(caplog):
    result = analyze_wheel_abi(
        None,
        None,
        HERE
        / "patchelf-0.17.2.1-py2.py3-none-manylinux_2_5_x86_64.manylinux1_x86_64.musllinux_1_1_x86_64.whl",
        frozenset(),
        False,
        False,
    )
    assert "setting architecture to x86_64" in caplog.text
    assert "couldn't detect wheel libc, defaulting to" in caplog.text
    assert result.policies.architecture == Architecture.x86_64
    if Libc.detect() == Libc.MUSL:
        assert result.policies.libc == Libc.MUSL
        assert result.overall_policy.name.startswith("musllinux_1_")
    else:
        assert result.policies.libc == Libc.GLIBC
        assert result.overall_policy.name == "manylinux_2_5_x86_64"


@pytest.mark.parametrize(
    "timestamp",
    [
        (0, 315532800),  # zip timestamp starts 1980-01-01, not 1970-01-01
        (315532799, 315532800),  # zip timestamp starts 1980-01-01, not 1970-01-01
        (315532801, 315532800),  # zip timestamp round odd seconds down to even seconds
        (315532802, 315532802),
        (650203201, 650203200),  # zip timestamp round odd seconds down to even seconds
    ],
)
def test_wheel_source_date_epoch(timestamp, tmp_path, monkeypatch):
    wheel_path = (
        HERE / "arch-wheels/musllinux_1_2/testsimple-0.0.1-cp312-cp312-linux_x86_64.whl"
    )
    wheel_output_path = tmp_path / "out"
    args = Namespace(
        LIB_SDIR=".libs",
        ONLY_PLAT=False,
        PLAT="auto",
        STRIP=False,
        UPDATE_TAGS=True,
        WHEEL_DIR=wheel_output_path,
        WHEEL_FILE=[wheel_path],
        EXCLUDE=[],
        DISABLE_ISA_EXT_CHECK=False,
        ZIP_COMPRESSION_LEVEL=6,
        cmd="repair",
        func=Mock(),
        prog="auditwheel",
        verbose=1,
    )

    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(timestamp[0]))
    main_repair.execute(args, Mock())
    output_wheel, *_ = list(wheel_output_path.glob("*.whl"))
    with zipfile.ZipFile(output_wheel) as wheel_file:
        for file in wheel_file.infolist():
            file_date_time = datetime(*file.date_time, tzinfo=timezone.utc)
            assert file_date_time.timestamp() == timestamp[1]


def test_libpython(tmp_path, caplog):
    wheel = HERE / "python_mscl-67.0.1.0-cp313-cp313-manylinux2014_aarch64.whl"
    args = Namespace(
        LIB_SDIR=".libs",
        ONLY_PLAT=False,
        PLAT="auto",
        STRIP=False,
        UPDATE_TAGS=True,
        WHEEL_DIR=tmp_path,
        WHEEL_FILE=[wheel],
        EXCLUDE=[],
        DISABLE_ISA_EXT_CHECK=False,
        ZIP_COMPRESSION_LEVEL=6,
        cmd="repair",
        func=Mock(),
        prog="auditwheel",
        verbose=0,
    )
    main_repair.execute(args, Mock())
    assert (
        "Removing libpython3.13.so.1.0 dependency from python_mscl/_mscl.so"
        in caplog.text
    )
    assert tuple(path.name for path in tmp_path.glob("*.whl")) == (
        "python_mscl-67.0.1.0-cp313-cp313-manylinux2014_aarch64.manylinux_2_31_aarch64.whl",
    )
