from __future__ import annotations

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
    assert "usage: auditwheel [-h] [-V] [-v] [-j MAX_JOBS] command ..." in captured.out
