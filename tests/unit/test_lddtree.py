import os
from pathlib import Path

import pytest

from auditwheel import lddtree
from auditwheel.architecture import Architecture
from auditwheel.lddtree import LIBPYTHON_RE, ld_paths_from_arg, ldd, load_ld_paths, parse_ld_paths
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
        ("", "", {"conf": [], "auditwheel": [], "env": [], "interp": []}),
        (str(HERE), "", {"conf": [str(HERE)], "auditwheel": [], "env": [], "interp": []}),
        ("", str(HERE), {"conf": [], "auditwheel": [str(HERE)], "env": [], "interp": []}),
        (
            str(HERE),
            str(HERE.parent),
            {"conf": [str(HERE)], "auditwheel": [str(HERE.parent)], "env": [], "interp": []},
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


def test_load_ld_paths_root_scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """root != '/' should ignore standard LD_LIBRARY_PATH but retain AUDITWHEEL_LD_LIBRARY_PATH."""
    auditwheel_dir = tmp_path / "auditwheel"
    auditwheel_dir.mkdir()
    ld_dir = tmp_path / "ld_library_path"
    ld_dir.mkdir()

    monkeypatch.setitem(os.environ, "AUDITWHEEL_LD_LIBRARY_PATH", str(auditwheel_dir))
    monkeypatch.setitem(os.environ, "LD_LIBRARY_PATH", str(ld_dir))

    # root is non-root
    fake_root = tmp_path / "fake_root"
    fake_root.mkdir()

    res = load_ld_paths(Libc.GLIBC, root=str(fake_root))
    assert res["auditwheel"] == [str(auditwheel_dir)]
    assert res["env"] == []


def test_runpath_vs_auditwheel_and_ld_library_path_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify precedence order: AUDITWHEEL_LD_LIBRARY_PATH > RUNPATH > LD_LIBRARY_PATH."""
    wheel = BUNDLED_WHEELS / "testzlib-0.0.1-cp310-cp310-linux_x86_64.whl"
    so = tmp_path / "testzlib.cpython-310-x86_64-linux-gnu.so"
    zip2dir(wheel, tmp_path)

    # Prepare directories with fake libz.so.1 (use valid ELF bytes from testzlib so)
    valid_elf_bytes = so.read_bytes()

    dir_auditwheel = tmp_path / "dir_auditwheel"
    dir_auditwheel.mkdir()
    (dir_auditwheel / "libz.so.1").write_bytes(valid_elf_bytes)

    dir_runpath = tmp_path / "dir_runpath"
    dir_runpath.mkdir()
    (dir_runpath / "libz.so.1").write_bytes(valid_elf_bytes)

    dir_ld_lib = tmp_path / "dir_ld_lib"
    dir_ld_lib.mkdir()
    (dir_ld_lib / "libz.so.1").write_bytes(valid_elf_bytes)

    orig_iter_segments = lddtree.ELFFile.iter_segments

    def mocked_iter_segments(self):
        for seg in orig_iter_segments(self):
            if seg.header.p_type == "PT_DYNAMIC":
                orig_iter_tags = getattr(seg, "iter_tags")  # noqa: B009

                def mocked_iter_tags(tags_fn=orig_iter_tags):
                    yield from tags_fn()
                    entry = type("Entry", (), {"d_tag": "DT_RUNPATH"})()
                    yield type(
                        "MockTag",
                        (),
                        {"entry": entry, "runpath": str(dir_runpath)},
                    )()

                seg.iter_tags = mocked_iter_tags  # type: ignore[attr-defined]
            yield seg

    monkeypatch.setattr(lddtree.ELFFile, "iter_segments", mocked_iter_segments)

    # 1. RUNPATH vs normal LD_LIBRARY_PATH (PR #4 historical behavior: RUNPATH must win)
    lddtree.load_ld_paths.cache_clear()
    monkeypatch.delenv("AUDITWHEEL_LD_LIBRARY_PATH", raising=False)
    monkeypatch.setitem(os.environ, "LD_LIBRARY_PATH", str(dir_ld_lib))
    res1 = ldd(so)
    assert res1.libraries["libz.so.1"].path == str(dir_runpath / "libz.so.1")

    # 2. RUNPATH vs AUDITWHEEL_LD_LIBRARY_PATH (Issue #737: AUDITWHEEL must win)
    lddtree.load_ld_paths.cache_clear()
    monkeypatch.setitem(os.environ, "AUDITWHEEL_LD_LIBRARY_PATH", str(dir_auditwheel))
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    res2 = ldd(so)
    assert res2.libraries["libz.so.1"].path == str(dir_auditwheel / "libz.so.1")

    # 3. Triple precedence: AUDITWHEEL_LD_LIBRARY_PATH > RUNPATH > LD_LIBRARY_PATH
    lddtree.load_ld_paths.cache_clear()
    monkeypatch.setitem(os.environ, "AUDITWHEEL_LD_LIBRARY_PATH", str(dir_auditwheel))
    monkeypatch.setitem(os.environ, "LD_LIBRARY_PATH", str(dir_ld_lib))
    res3 = ldd(so)
    assert res3.libraries["libz.so.1"].path == str(dir_auditwheel / "libz.so.1")

    # 4. Backward compatibility: custom ldpaths dict without 'auditwheel' key
    # Ensure no KeyError is raised and original search behavior is preserved
    custom_ldpaths = {
        "rpath": [],
        "runpath": [],
        "conf": [str(dir_runpath)],
        "env": [str(dir_ld_lib)],
        "interp": [],
    }
    res4 = ldd(so, ldpaths=custom_ldpaths)
    assert res4.libraries["libz.so.1"].path == str(dir_runpath / "libz.so.1")
