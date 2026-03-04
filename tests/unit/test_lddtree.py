import os
from pathlib import Path

import pytest

from auditwheel.architecture import Architecture
from auditwheel.lddtree import LIBPYTHON_RE, ldd, parse_ld_paths
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


def test_parse_ld_paths():
    here = str(HERE)
    parent = str(HERE.parent)

    assert parse_ld_paths("") == []
    assert parse_ld_paths(f"{here}") == [here]
    assert parse_ld_paths(f"{parent}") == [parent]

    # Order is preserved.
    assert parse_ld_paths(f"{here}:{parent}") == [here, parent]
    assert parse_ld_paths(f"{parent}:{here}") == [parent, here]

    # `..` references are normalized.
    assert parse_ld_paths(f"{here}/..") == [parent]

    # Duplicate paths are deduplicated.
    assert parse_ld_paths(f"{here}:{here}") == [here]

    # Empty paths are equivalent to $PWD.
    cwd = str(Path.cwd())
    assert parse_ld_paths(":") == [cwd]
    assert parse_ld_paths(f"{here}:") == [here, cwd]
    assert parse_ld_paths(f":{here}") == [cwd, here]

    # Nonexistent paths are ignored.
    assert parse_ld_paths("/nonexistent") == []
    assert parse_ld_paths(f"/nonexistent:{here}") == [here]


@pytest.mark.parametrize("origin", ["$ORIGIN", "${ORIGIN}"])
def test_parse_ld_paths_origin(origin):
    here = str(HERE)
    parent = str(HERE.parent)

    with pytest.raises(ValueError, match=r"can't expand \$ORIGIN without a path"):
        parse_ld_paths(origin)

    assert parse_ld_paths(origin, path=__file__) == [here]
    assert parse_ld_paths(f"{origin}/..", path=__file__) == [parent]

    # Relative paths are made absolute.
    assert parse_ld_paths(origin, path=os.path.relpath(__file__)) == [here]
