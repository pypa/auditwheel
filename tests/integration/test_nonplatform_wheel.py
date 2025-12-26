from __future__ import annotations

import pathlib
import subprocess

import pytest

from auditwheel.architecture import Architecture

HERE = pathlib.Path(__file__).parent.resolve()


@pytest.mark.parametrize("mode", ["repair", "show"])
def test_non_platform_wheel_pure(mode):
    wheel = HERE / "plumbum-1.6.8-py2.py3-none-any.whl"
    proc = subprocess.run(
        ["auditwheel", mode, str(wheel)],
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "This does not look like a platform wheel" in proc.stderr
    assert "AttributeError" not in proc.stderr


@pytest.mark.parametrize("mode", ["repair", "show"])
@pytest.mark.parametrize("arch", ["armv5l", "mips64"])
def test_non_platform_wheel_unknown_arch(mode, arch, tmp_path):
    wheel_name = f"testsimple-0.0.1-cp313-cp313-linux_{arch}.whl"
    wheel_path = HERE / "arch-wheels" / "glibc" / wheel_name
    wheel_x86_64 = tmp_path / f"{wheel_path.stem}_x86_64.whl"
    wheel_x86_64.symlink_to(wheel_path)
    proc = subprocess.run(
        ["auditwheel", mode, str(wheel_x86_64)],
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "Invalid binary wheel: no ELF executable or" in proc.stderr
    assert "unknown architecture" in proc.stderr
    assert "AttributeError" not in proc.stderr


@pytest.mark.parametrize("mode", ["repair", "show"])
@pytest.mark.parametrize(
    "arch",
    ["aarch64", "armv7l", "i686", "x86_64", "ppc64le", "s390x"],
)
def test_non_platform_wheel_bad_arch(mode, arch, tmp_path):
    host_arch = Architecture.detect().value
    if host_arch == arch:
        pytest.skip("host architecture")
    wheel_name = f"testsimple-0.0.1-cp313-cp313-linux_{arch}.whl"
    wheel_path = HERE / "arch-wheels" / "glibc" / wheel_name
    wheel_host = tmp_path / f"{wheel_path.stem}_{host_arch}.whl"
    wheel_host.symlink_to(wheel_path)
    proc = subprocess.run(
        ["auditwheel", mode, str(wheel_host)],
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "Invalid binary wheel: no ELF executable or" in proc.stderr
    assert f"{arch} architecture" in proc.stderr
    assert "AttributeError" not in proc.stderr
