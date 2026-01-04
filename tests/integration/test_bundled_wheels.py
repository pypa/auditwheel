from __future__ import annotations

import importlib
import json
import os
import sys
import zipfile
from argparse import Namespace
from datetime import datetime, timezone
from os.path import isabs
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from auditwheel import lddtree, main_repair
from auditwheel.architecture import Architecture
from auditwheel.libc import Libc
from auditwheel.main import main
from auditwheel.wheel_abi import NonPlatformWheelError, analyze_wheel_abi

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

    with pytest.MonkeyPatch.context() as cp:
        if modify_ld_library_path:
            cp.setenv("LD_LIBRARY_PATH", f"{HERE}")
            importlib.reload(lddtree)

        winfo = analyze_wheel_abi(
            Libc.GLIBC,
            Architecture.x86_64,
            HERE / file,
            exclude,
            disable_isa_ext_check=False,
            allow_graft=True,
        )
        assert set(winfo.external_refs["manylinux_2_5_x86_64"].libs) == external_libs, (
            f"{HERE}, {exclude}, {os.environ}"
        )

    if modify_ld_library_path:
        importlib.reload(lddtree)


def test_analyze_wheel_abi_pyfpe():
    winfo = analyze_wheel_abi(
        Libc.GLIBC,
        Architecture.x86_64,
        HERE / "fpewheel-0.0.0-cp35-cp35m-linux_x86_64.whl",
        frozenset(),
        disable_isa_ext_check=False,
        allow_graft=True,
    )
    # for external symbols, it could get manylinux1
    assert winfo.sym_policy.name == "manylinux_2_5_x86_64"
    # but for having the pyfpe reference, it gets just linux
    assert winfo.pyfpe_policy.name == "linux_x86_64"
    assert winfo.overall_policy.name == "linux_x86_64"


def test_show_wheel_abi_pyfpe(monkeypatch, capsys):
    wheel = str(HERE / "fpewheel-0.0.0-cp35-cp35m-linux_x86_64.whl")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Architecture, "detect", lambda: Architecture.x86_64)
    monkeypatch.setattr(sys, "argv", ["auditwheel", "show", wheel])
    assert main() == 0
    captured = capsys.readouterr()
    assert "This wheel uses the PyFPE_jbuf function" in captured.out


def test_analyze_wheel_abi_bad_architecture():
    with pytest.raises(NonPlatformWheelError):
        analyze_wheel_abi(
            Libc.GLIBC,
            Architecture.aarch64,
            HERE / "fpewheel-0.0.0-cp35-cp35m-linux_x86_64.whl",
            frozenset(),
            disable_isa_ext_check=False,
            allow_graft=True,
        )


def test_analyze_wheel_abi_static_exe(caplog):
    result = analyze_wheel_abi(
        None,
        None,
        HERE
        / "patchelf-0.17.2.1-py2.py3-none-manylinux_2_5_x86_64.manylinux1_x86_64.musllinux_1_1_x86_64.whl",  # noqa: E501
        frozenset(),
        disable_isa_ext_check=False,
        allow_graft=False,
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
    wheel_path = HERE / "arch-wheels/musllinux_1_2/testsimple-0.0.1-cp312-cp312-linux_x86_64.whl"
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
    assert "Removing libpython3.13.so.1.0 dependency from python_mscl/_mscl.so" in caplog.text
    assert tuple(path.name for path in tmp_path.glob("*.whl")) == (
        "python_mscl-67.0.1.0-cp313-cp313-manylinux2014_aarch64.manylinux_2_31_aarch64.whl",
    )


def test_main_lddtree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    wheel_path = (
        HERE
        / "patchelf-0.17.2.1-py2.py3-none-manylinux_2_5_x86_64.manylinux1_x86_64.musllinux_1_1_x86_64.whl"  # noqa: E501
    )
    patchelf_path = tmp_path / "patchelf-0.17.2.1.data/scripts/patchelf"
    with zipfile.ZipFile(wheel_path) as f:
        f.extract(str(patchelf_path.relative_to(tmp_path)), tmp_path)
    patchelf_path = patchelf_path.resolve(strict=True)

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Architecture, "detect", lambda: Architecture.x86_64)
    monkeypatch.setattr(sys, "argv", ["auditwheel", "lddtree", str(patchelf_path)])
    assert main() == 0
    assert len(caplog.messages) == 1
    actual_json = json.loads(caplog.messages[0])
    expected_json: Any = {
        "interpreter": None,
        "libc": None,
        "path": str(patchelf_path),
        "realpath": str(patchelf_path),
        "platform": {
            "_elf_osabi": "ELFOSABI_SYSV",
            "_elf_class": 64,
            "_elf_little_endian": True,
            "_elf_machine": "EM_X86_64",
            "_base_arch": "<Architecture.x86_64: 'x86_64'>",
            "_ext_arch": None,
            "_error_msg": None,
        },
        "needed": [],
        "rpath": [],
        "runpath": [],
        "libraries": {},
    }
    assert expected_json == actual_json


def test_weak_symbols_not_blacklisted() -> None:
    # https://github.com/pypa/auditwheel/issues/663
    # the cryptography wheel overall policy was misclassified as manylinux_2_24_x86_64
    # in auditwheel 6.5.1 because it uses the undefined weak symbol '__cxa_thread_atexit_impl'
    result = analyze_wheel_abi(
        None,
        None,
        HERE / "cryptography-46.0.3-cp38-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
        frozenset(),
        disable_isa_ext_check=False,
        allow_graft=False,
    )
    assert result.policies.libc == Libc.GLIBC
    assert result.policies.architecture == Architecture.x86_64
    assert result.overall_policy.name == "manylinux_2_17_x86_64"
