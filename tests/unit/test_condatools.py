from unittest.mock import patch, Mock

from auditwheel.condatools import InCondaPkg, InCondaPkgCtx


@patch("auditwheel.condatools.tarbz2todir")
def test_in_condapkg(tarbz2todir_mock):
    with InCondaPkg("/fakepath"):
        assert True


@patch("auditwheel.condatools.tarbz2todir")
@patch("auditwheel.condatools.open")
def test_in_condapkg_context(open_mock, tarbz2todir_mock):
    with InCondaPkgCtx("/fakepath") as conda_pkg:
        file_mock = Mock()
        file_mock.readlines.return_value = ["file1\n", "file2\n", "\n"]
        open_mock.return_value.__enter__.return_value = file_mock
        # This returns empty lines so we have count with those as well. This
        # might be a subtle bug in the implementation.
        files = conda_pkg.iter_files()
        assert len(files) == 3
        assert "file1" and "file2" in files

