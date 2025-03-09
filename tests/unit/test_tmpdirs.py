from __future__ import annotations

from pathlib import Path

import pytest

from auditwheel.tmpdirs import InGivenDirectory, InTemporaryDirectory


def test_intemporarydirectory() -> None:
    cwd = Path.cwd()
    with InTemporaryDirectory() as path:
        assert path.is_dir()
        assert path.samefile(Path.cwd())
        assert not path.samefile(cwd)
    assert not path.exists()
    assert cwd.samefile(Path.cwd())


def test_intemporarydirectory_name() -> None:
    tmp_dir = InTemporaryDirectory()
    with tmp_dir as path:
        assert tmp_dir.name == path


def test_ingivendirectory(tmp_path: Path) -> None:
    cwd = Path.cwd()
    expected_path = tmp_path / "foo"
    with InGivenDirectory(expected_path) as path:
        assert path.is_dir()
        assert path.samefile(Path.cwd())
        assert path.samefile(expected_path)
    assert path.exists()
    assert cwd.samefile(Path.cwd())


def test_ingivendirectory_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    with InGivenDirectory() as path:
        assert path.is_dir()
        assert path.samefile(Path.cwd())
        assert path.samefile(tmp_path)
    assert path.exists()


def test_ingivendirectory_name():
    given_dir = InGivenDirectory()
    with given_dir as path:
        assert given_dir.name == path
