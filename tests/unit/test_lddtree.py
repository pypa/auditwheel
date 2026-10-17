import os
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from elftools.elf.elffile import ELFFile

from auditwheel import lddtree
from auditwheel.architecture import Architecture
from auditwheel.lddtree import LIBPYTHON_RE, ld_paths_from_arg, ldd, parse_ld_paths
from auditwheel.libc import Libc
from auditwheel.tools import zip2dir

HERE = Path(__file__).parent.resolve(strict=True)
BUNDLED_WHEELS = HERE / ".." / "bundled-wheels"


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
    wheel = BUNDLED_WHEELS / "python_mscl-67.0.1.0-cp313-cp313-manylinux2014_aarch64.whl"
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


@pytest.mark.parametrize(
    ("arg", "env", "expected"),
    [
        (None, "", None),
        (None, str(HERE.parent), None),
        ("", "", {"conf": [], "env": [], "interp": []}),
        (str(HERE), "", {"conf": [str(HERE)], "env": [], "interp": []}),
        ("", str(HERE), {"conf": [], "env": [str(HERE)], "interp": []}),
        (
            str(HERE),
            str(HERE.parent),
            {"conf": [str(HERE)], "env": [str(HERE.parent)], "interp": []},
        ),
    ],
)
def test_ld_paths_from_arg(arg, env, expected, monkeypatch):
    monkeypatch.setitem(os.environ, "AUDITWHEEL_LD_LIBRARY_PATH", env)
    assert ld_paths_from_arg(arg) == expected


def test_libc_no_detect_musl_cp310(tmp_path: Path) -> None:
    wheel = BUNDLED_WHEELS / "musllinux_1_2/testsimple-0.0.1-cp310-cp310-linux_x86_64.whl"
    so = tmp_path / "testsimple.cpython-310-x86_64-linux-gnu.so"
    zip2dir(wheel, tmp_path)
    result = ldd(so)
    assert result.interpreter is None
    assert result.libc is None  # we can't detect libc for this library
    assert result.platform.baseline_architecture == Architecture.x86_64
    assert result.platform.extended_architecture is None
    assert result.path is not None
    assert result.realpath.samefile(so)
    assert result.needed == ()
    assert result.rpath == ()
    assert result.runpath == ()
    assert not result.libraries


@pytest.mark.parametrize("stack_flags", [None, 6, 7], ids=["absent", "rw", "rwx"])
def test_ldd_caches_stack_requirement(stack_flags, tmp_path):
    wheel = BUNDLED_WHEELS / "glibc/testsimple-0.0.1-cp313-cp313-linux_x86_64.whl"
    zip2dir(wheel, tmp_path)
    so = next(tmp_path.glob("*.so"))
    data = bytearray(so.read_bytes())
    elf = ELFFile(BytesIO(data))
    changed = 0
    for index, segment in enumerate(elf.iter_segments()):
        if segment.header.p_type != "PT_GNU_STACK":
            continue
        changed += 1
        header = segment.header
        if stack_flags is None:
            header.p_type = "PT_NULL"
        else:
            header.p_flags = stack_flags
        offset = elf.header.e_phoff + index * elf.header.e_phentsize
        data[offset : offset + elf.header.e_phentsize] = elf.structs.Elf_Phdr.build(header)
    assert changed == 1
    so.write_bytes(data)
    result = ldd(so, ldpaths={"conf": [], "env": [], "interp": []})
    assert result.executable_stack is (None if stack_flags is None else bool(stack_flags & 1))


@pytest.mark.parametrize("stack_requirement", [False, None, True])
def test_ldd_propagates_dependency_stack_requirement(stack_requirement, tmp_path, monkeypatch):
    wheel = BUNDLED_WHEELS / "python_mscl-67.0.1.0-cp313-cp313-manylinux2014_aarch64.whl"
    zip2dir(wheel, tmp_path)
    so = tmp_path / "python_mscl" / "_mscl.so"
    # Reuse a real ELF for the dependency; mark recursive instances as dependency-free.
    original_ldd = lddtree.ldd
    dependency_path = tmp_path / "libexample.so"
    dependency_path.write_bytes(so.read_bytes())

    def dependency_ldd(path, *_args):
        assert path == dependency_path
        result = original_ldd(
            path,
            ldpaths={"conf": [], "env": [], "interp": []},
            exclude=frozenset({"*"}),
        )
        return replace(result, executable_stack=stack_requirement)

    monkeypatch.setattr(lddtree, "find_lib", lambda *_: (dependency_path, str(dependency_path)))
    monkeypatch.setattr(lddtree, "ldd", dependency_ldd)
    result = original_ldd(so, ldpaths={"conf": [], "env": [], "interp": []})
    resolved = [library for library in result.libraries.values() if library.realpath is not None]
    assert resolved
    assert all(library.executable_stack is stack_requirement for library in resolved)
