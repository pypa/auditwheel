from __future__ import annotations

import subprocess
import sys
from importlib import metadata

import pytest

from auditwheel.architecture import Architecture
from auditwheel.libc import Libc, LibcVersion
from auditwheel.main import main

on_supported_platform = pytest.mark.skipif(
    sys.platform != "linux",
    reason="requires Linux system",
)


def test_unsupported_platform(monkeypatch):
    # GIVEN
    monkeypatch.setattr(sys, "platform", "unsupported_platform")

    # WHEN
    retval = main()

    # THEN
    assert retval == 1


@on_supported_platform
def test_help(monkeypatch, capsys):
    # GIVEN
    monkeypatch.setattr(sys, "argv", ["auditwheel"])

    # WHEN
    retval = main()

    # THEN
    assert retval is None
    captured = capsys.readouterr()
    assert "usage: auditwheel [-h] [-V] [-v] command ..." in captured.out


@pytest.mark.parametrize("function", ["show", "repair"])
def test_unexisting_wheel(monkeypatch, capsys, tmp_path, function):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Architecture, "detect", lambda: Architecture.x86_64)
    wheel = str(tmp_path / "not-a-file.whl")
    monkeypatch.setattr(sys, "argv", ["auditwheel", function, wheel])

    with pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert "No such file" in captured.err


@pytest.mark.parametrize(
    ("libc", "filename", "plat", "message"),
    [
        (
            Libc.GLIBC,
            "foo-1.0-py3-none-manylinux1_aarch64.whl",
            "manylinux_2_28_x86_64",
            "can't repair wheel foo-1.0-py3-none-manylinux1_aarch64.whl with aarch64 architecture to a wheel targeting x86_64",  # noqa: E501
        ),
        (
            Libc.GLIBC,
            "foo-1.0-py3-none-musllinux_1_1_x86_64.whl",
            "manylinux_2_28_x86_64",
            "can't repair wheel foo-1.0-py3-none-musllinux_1_1_x86_64.whl with MUSL libc to a wheel targeting GLIBC",  # noqa: E501
        ),
        (
            Libc.MUSL,
            "foo-1.0-py3-none-manylinux1_x86_64.whl",
            "musllinux_1_1_x86_64",
            "can't repair wheel foo-1.0-py3-none-manylinux1_x86_64.whl with GLIBC libc to a wheel targeting MUSL",  # noqa: E501
        ),
    ],
)
def test_repair_wheel_mismatch(
    monkeypatch,
    capsys,
    tmp_path,
    libc,
    filename,
    plat,
    message,
):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Architecture, "detect", lambda: Architecture.x86_64)
    monkeypatch.setattr(Libc, "detect", lambda: libc)
    monkeypatch.setattr(Libc, "get_current_version", lambda _: LibcVersion(1, 1))
    wheel = tmp_path / filename
    wheel.write_text("")
    monkeypatch.setattr(
        sys,
        "argv",
        ["auditwheel", "repair", "--plat", plat, str(wheel)],
    )

    with pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert message in captured.err


@on_supported_platform
def test_main_module() -> None:
    version = metadata.version("auditwheel")
    result = subprocess.run(
        [sys.executable, "-m", "auditwheel", "-V"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.startswith(f"auditwheel {version}")
