from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from auditwheel.condatools import InCondaPkg, InCondaPkgCtx


@patch("auditwheel.condatools.tarbz2todir")
def test_in_condapkg(_):  # noqa: PT019
    with InCondaPkg(Path("/fakepath")):
        assert True


@patch("auditwheel.condatools.tarbz2todir")
@patch("auditwheel.condatools.open")
def test_in_condapkg_context(open_mock, _):  # noqa: PT019
    with InCondaPkgCtx(Path("/fakepath")) as conda_pkg:
        file_mock = Mock()
        file_mock.readlines.return_value = ["file1\n", "file2\n", "\n"]
        open_mock.return_value.__enter__.return_value = file_mock
        # This returns empty lines so we have count with those as well. This
        # might be a subtle bug in the implementation.
        files = conda_pkg.iter_files()
        assert len(files) == 3
        assert "file1" in files
        assert "file2" in files
