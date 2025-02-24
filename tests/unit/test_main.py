from __future__ import annotations

import platform
import sys

import pytest

from auditwheel.main import main

on_supported_platform = pytest.mark.skipif(
    sys.platform != "linux", reason="requires Linux system"
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


def test_show_unexisting_wheel(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    wheel = str(tmp_path / "not-a-file.whl")
    monkeypatch.setattr(sys, "argv", ["dummy", "show", wheel])

    with pytest.raises(SystemExit):
        main()

    captured = capsys.readouterr()
    assert "No such file" in captured.err
