import os
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from auditwheel.elfutils import elf_read_dt_needed, elf_read_rpaths, elf_read_soname

HERE = Path(__file__).parent.resolve()


@pytest.mark.parametrize("ldpaths_methods", [["env"], ["arg"], ["env", "arg"]])
def test_libcxx(ldpaths_methods, tmp_path):
    # This wheel was generated from cibuildwheel's test_android.py::test_libcxx. It contains an
    # external reference to libc++_shared.so.
    android_dir = HERE / "android"
    input_wheel = android_dir / "spam-0.1.0-cp313-cp313-android_24_arm64_v8a.whl"

    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()

    # The dummy libc++_shared.so files were generated using this command, where SUBDIR is either
    # "env" or "arg":
    #     echo "void SUBDIR() {}"
    #     | aarch64-linux-android24-clang -x c - -shared -o SUBDIR/libc++_shared.so
    ldpaths = ""
    if "arg" in ldpaths_methods:
        libcxx_hash = "1be9716c"
        ldpaths = str(android_dir / "ldpaths/arg")

    env = os.environ.copy()
    if "env" in ldpaths_methods:
        # LD_LIBRARY_PATH takes priority over --ldpaths, so we overwrite the hash.
        libcxx_hash = "18b6a03d"
        env["LD_LIBRARY_PATH"] = str(android_dir / "ldpaths/env")

    subprocess.run(
        ["auditwheel", "repair", "-w", wheelhouse, "--ldpaths", ldpaths, input_wheel],
        env=env,
        text=True,
        check=True,
    )
    output_wheels = list(wheelhouse.iterdir())
    assert len(output_wheels) == 1
    assert output_wheels[0].name == input_wheel.name

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    with ZipFile(output_wheels[0]) as zf:
        zf.extractall(output_dir)

    libs_dir = output_dir / "spam.libs"
    libcxx_path = libs_dir / f"libc++_shared-{libcxx_hash}.so"
    assert elf_read_soname(libcxx_path) == libcxx_path.name
    assert elf_read_rpaths(libcxx_path) == {"rpaths": [], "runpaths": [str(libs_dir)]}

    spam_path = output_dir / "spam.cpython-313-aarch64-linux-android.so"
    assert set(elf_read_dt_needed(spam_path)) == {
        # Included in the policy
        "libc.so",
        "libdl.so",
        "libm.so",
        # libpython dependency is normal on Android, so it should be left alone
        "libpython3.13.so",
        # Grafted library
        libcxx_path.name,
    }
    assert elf_read_rpaths(spam_path) == {"rpaths": [], "runpaths": [str(libs_dir)]}
