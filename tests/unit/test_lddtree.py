from pathlib import Path

from auditwheel.architecture import Architecture
from auditwheel.lddtree import ldd
from auditwheel.libc import Libc
from auditwheel.tools import zip2dir

HERE = Path(__file__).parent.resolve(strict=True)


def test_libpython(tmp_path: Path, caplog):
    wheel = (
        HERE
        / ".."
        / "integration"
        / "python_mscl-67.0.1.0-cp313-cp313-manylinux2014_aarch64.whl"
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
