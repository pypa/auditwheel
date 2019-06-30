import os
from auditwheel.tmpdirs import InTemporaryDirectory, InGivenDirectory


def test_intemporarydirectory():
    cwd = os.getcwd()
    with InTemporaryDirectory() as path:
        assert os.path.isdir(path)
        assert os.path.samefile(path, os.getcwd())
        assert not os.path.samefile(cwd, path)
    assert not os.path.exists(path)
    assert os.path.samefile(cwd, os.getcwd())


def test_intemporarydirectory_name():
    tmp_dir = InTemporaryDirectory()
    with tmp_dir as path:
        assert tmp_dir.name == path


def test_ingivendirectory(tmp_path):
    cwd = os.getcwd()
    expected_path = os.path.join(str(tmp_path), 'foo')
    with InGivenDirectory(expected_path) as path:
        assert os.path.isdir(path)
        assert os.path.samefile(path, os.getcwd())
        assert os.path.samefile(path, expected_path)
    assert os.path.exists(path)
    assert os.path.samefile(cwd, os.getcwd())


def test_ingivendirectory_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with InGivenDirectory() as path:
        assert os.path.isdir(path)
        assert os.path.samefile(path, os.getcwd())
        assert os.path.samefile(path, str(tmp_path))
    assert os.path.exists(path)


def test_ingivendirectory_name():
    given_dir = InGivenDirectory()
    with given_dir as path:
        assert given_dir.name == path
