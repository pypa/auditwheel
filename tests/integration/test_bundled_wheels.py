import platform
import subprocess
import sys
import zipfile
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from unittest.mock import Mock

import pytest

from auditwheel import main_repair
from auditwheel.wheel_abi import analyze_wheel_abi

HERE = Path(__file__).parent.resolve()


@pytest.mark.skipif(platform.machine() != "x86_64", reason="only supported on x86_64")
@pytest.mark.parametrize(
    "file, external_libs",
    [
        ("cffi-1.5.0-cp27-none-linux_x86_64.whl", {"libffi.so.5"}),
        ("python_snappy-0.5.2-pp260-pypy_41-linux_x86_64.whl", {"libsnappy.so.1"}),
    ],
)
def test_analyze_wheel_abi(file, external_libs):
    winfo = analyze_wheel_abi(str(HERE / file))
    assert set(winfo.external_refs["manylinux_2_5_x86_64"]["libs"]) == external_libs


@pytest.mark.skipif(platform.machine() != "x86_64", reason="only supported on x86_64")
def test_analyze_wheel_abi_pyfpe():
    winfo = analyze_wheel_abi(str(HERE / "fpewheel-0.0.0-cp35-cp35m-linux_x86_64.whl"))
    assert (
        winfo.sym_tag == "manylinux_2_5_x86_64"
    )  # for external symbols, it could get manylinux1
    assert (
        winfo.pyfpe_tag == "linux_x86_64"
    )  # but for having the pyfpe reference, it gets just linux


@pytest.mark.skipif(platform.machine() != "x86_64", reason="only checked on x86_64")
def test_wheel_source_date_epoch(tmp_path, monkeypatch):
    wheel_build_path = tmp_path / "wheel"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "-w",
            wheel_build_path,
            HERE / "sample_extension",
        ],
        check=True,
    )

    wheel_path, *_ = list(wheel_build_path.glob("*.whl"))
    wheel_output_path = tmp_path / "out"
    args = Namespace(
        LIB_SDIR=".libs",
        ONLY_PLAT=False,
        PLAT="manylinux_2_5_x86_64",
        STRIP=False,
        UPDATE_TAGS=True,
        WHEEL_DIR=str(wheel_output_path),
        WHEEL_FILE=str(wheel_path),
        cmd="repair",
        func=Mock(),
        prog="auditwheel",
        verbose=1,
    )
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "650203200")
    # patchelf might not be available as we aren't running in a manylinux container
    # here. We don't need need it in this test, so just patch it.
    with mock.patch("auditwheel.patcher._verify_patchelf"):
        main_repair.execute(args, Mock())

    output_wheel, *_ = list(wheel_output_path.glob("*.whl"))
    with zipfile.ZipFile(output_wheel) as wheel_file:
        for file in wheel_file.infolist():
            assert (
                datetime(*file.date_time, tzinfo=timezone.utc).timestamp() == 650203200
            )
