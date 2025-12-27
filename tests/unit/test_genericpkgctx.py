import pytest

from auditwheel.genericpkgctx import InGenericPkgCtx


def test_unknown_extension(tmp_path):
    file = tmp_path / "foo.txt"
    file.touch()
    with pytest.raises(ValueError, match=r".*File formats supported.*"):
        InGenericPkgCtx(file)


def test_conda_outpath(tmp_path):
    file = tmp_path / "foo.tar.bz2"
    file.touch()
    out = tmp_path / "out.tar.bz2"
    with pytest.raises(NotImplementedError):
        InGenericPkgCtx(file, out)


@pytest.mark.parametrize("ext", ["whl", "tar.bz2"])
def test_valid_ext(tmp_path, ext):
    file = tmp_path / f"foo.{ext}"
    file.touch()
    InGenericPkgCtx(file)
