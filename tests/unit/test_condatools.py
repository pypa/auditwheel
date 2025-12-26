from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from auditwheel.condatools import InCondaPkg, InCondaPkgCtx


@patch("auditwheel.condatools.tarbz2todir")
def test_in_condapkg(_):  # noqa: PT019
    with InCondaPkg(Path("/fakepath")):
        assert True


@patch("auditwheel.condatools.tarbz2todir")
def test_in_condapkg_context(_):  # noqa: PT019
    with InCondaPkgCtx(Path("/fakepath")) as conda_pkg:
        # mock info/files
        files_path = conda_pkg.path / "info" / "files"
        files_path.parent.mkdir()
        files_path.write_text("file1\nfile2\n\n")
        # This returns empty lines so we have count with those as well. This
        # might be a subtle bug in the implementation.
        files = conda_pkg.iter_files()
        assert len(files) == 3
        assert "file1" in files
        assert "file2" in files
