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
def test_non_platform_wheel_unknown_arch(mode, arch):
    wheel = HERE / "arch-wheels" / f"testsimple-0.0.1-cp313-cp313-linux_{arch}.whl"
    proc = subprocess.run(
        ["auditwheel", mode, str(wheel)],
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
    "arch", ["aarch64", "armv7l", "i686", "x86_64", "ppc64le", "s390x"]
)
def test_non_platform_wheel_bad_arch(mode, arch):
    if Architecture.get_native_architecture().value == arch:
        pytest.skip("host architecture")
    wheel = HERE / "arch-wheels" / f"testsimple-0.0.1-cp313-cp313-linux_{arch}.whl"
    proc = subprocess.run(
        ["auditwheel", mode, str(wheel)],
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "Invalid binary wheel: no ELF executable or" in proc.stderr
    assert f"{arch} architecture" in proc.stderr
    assert "AttributeError" not in proc.stderr
