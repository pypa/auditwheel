from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

from auditwheel.architecture import Architecture
from auditwheel.error import NonPlatformWheel
from auditwheel.libc import Libc
from auditwheel.wheeltools import (
    InWheelCtx,
    WheelToolsError,
    get_wheel_architecture,
    get_wheel_libc,
)

HERE = Path(__file__).parent.resolve()


@pytest.mark.parametrize(
    ("filename", "expected"),
    [(f"foo-1.0-py3-none-linux_{arch}.whl", arch) for arch in Architecture]
    + [("foo-1.0-py3-none-linux_x86_64.manylinux1_x86_64.whl", Architecture.x86_64)],
)
def test_get_wheel_architecture(filename: str, expected: Architecture) -> None:
    arch = get_wheel_architecture(filename)
    assert arch == expected.baseline


def test_get_wheel_architecture_unknown() -> None:
    with pytest.raises(WheelToolsError, match=re.escape("unknown architecture")):
        get_wheel_architecture("foo-1.0-py3-none-linux_mipsel.whl")


def test_get_wheel_architecture_pure() -> None:
    with pytest.raises(NonPlatformWheel):
        get_wheel_architecture("foo-1.0-py3-none-any.whl")


@pytest.mark.parametrize(
    "filename",
    [
        "foo-1.0-py3-none-linux_x86_64.linux_aarch64.whl",
        "foo-1.0-py3-none-linux_x86_64.linux_mipsel.whl",
        "foo-1.0-py3-none-linux_x86_64.any.whl",
    ],
)
def test_get_wheel_architecture_multiple(filename: str) -> None:
    match = re.escape("multiple architectures are not supported")
    with pytest.raises(WheelToolsError, match=match):
        get_wheel_architecture(filename)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("foo-1.0-py3-none-manylinux1_x86_64.whl", Libc.GLIBC),
        ("foo-1.0-py3-none-manylinux1_x86_64.manylinux2010_x86_64.whl", Libc.GLIBC),
        ("foo-1.0-py3-none-musllinux_1_1_x86_64.whl", Libc.MUSL),
    ],
)
def test_get_wheel_libc(filename: str, expected: Libc) -> None:
    libc = get_wheel_libc(filename)
    assert libc == expected


@pytest.mark.parametrize(
    "filename", ["foo-1.0-py3-none-any.whl", "foo-1.0-py3-none-something.whl"]
)
def test_get_wheel_libc_unknown(filename: str) -> None:
    with pytest.raises(WheelToolsError, match=re.escape("unknown libc used")):
        get_wheel_libc(filename)


@pytest.mark.parametrize(
    "filename", ["foo-1.0-py3-none-manylinux1_x86_64.musllinux_1_1_x86_64.whl"]
)
def test_get_wheel_libc_multiple(filename: str) -> None:
    match = re.escape("multiple libc are not supported")
    with pytest.raises(WheelToolsError, match=match):
        get_wheel_libc(filename)


def test_inwheel_tmpdir(tmp_path, monkeypatch):
    wheel_path = (
        HERE
        / "../integration/arch-wheels/glibc/testsimple-0.0.1-cp313-cp313-linux_x86_64.whl"
    )
    tmp_path = tmp_path.resolve(strict=True)
    tmpdir = tmp_path / "tmpdir"
    tmpdir.mkdir()
    tmpdir_symlink = tmp_path / "symlink"
    tmpdir_symlink.symlink_to(str(tmpdir), target_is_directory=True)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmpdir_symlink))
    with InWheelCtx(wheel_path, tmp_path / wheel_path.name) as context:
        Path(context._tmpdir.name).relative_to(tmpdir_symlink)
        context.name.relative_to(tmpdir)
