from pathlib import Path

import pytest

from auditwheel.architecture import Architecture
from auditwheel.lddtree import LIBPYTHON_RE, ldd
from auditwheel.libc import Libc
from auditwheel.tools import zip2dir

HERE = Path(__file__).parent.resolve(strict=True)


@pytest.mark.parametrize(
    "soname",
    [
        "libpython3.7m.so.1.0",
        "libpython3.9.so.1.0",
        "libpython3.10.so.1.0",
        "libpython999.999.so.1.0",
    ],
)
def test_libpython_re_match(soname: str) -> None:
    assert LIBPYTHON_RE.match(soname)


@pytest.mark.parametrize(
    "soname",
    [
        "libpython3.7m.soa1.0",
        "libpython3.9.so.1a0",
    ],
)
def test_libpython_re_nomatch(soname: str) -> None:
    assert LIBPYTHON_RE.match(soname) is None


def test_libpython(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    wheel = (
        HERE / ".." / "integration" / "python_mscl-67.0.1.0-cp313-cp313-manylinux2014_aarch64.whl"
    )
    so = tmp_path / "python_mscl" / "_mscl.so"
    zip2dir(wheel, tmp_path)
    result = ldd(so)
    assert "Skip libpython3.13.so.1.0 resolution" in caplog.text
    assert result.interpreter is None
    assert result.libc == Libc.GLIBC
    assert result.platform.baseline_architecture == Architecture.aarch64
    assert result.platform.extended_architecture is None
    assert result.path is not None
    assert result.realpath.samefile(so)
    assert result.needed == (
        "libpython3.13.so.1.0",
        "libstdc++.so.6",
        "libm.so.6",
        "libgcc_s.so.1",
        "libc.so.6",
        "ld-linux-aarch64.so.1",
    )
    # libpython must be present in dependencies without path
    libpython = result.libraries["libpython3.13.so.1.0"]
    assert libpython.soname == "libpython3.13.so.1.0"
    assert libpython.path is None
    assert libpython.platform is None
    assert libpython.realpath is None
    assert libpython.needed == ()
