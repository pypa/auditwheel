from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

import pretend
import pytest

from auditwheel import wheel_abi
from auditwheel.architecture import Architecture
from auditwheel.lddtree import DynamicExecutable, DynamicLibrary, Platform
from auditwheel.libc import Libc
from auditwheel.policy import ExternalReference, WheelPolicies


class TestGetWheelElfdata:
    @pytest.mark.parametrize(
        ("filenames", "message"),
        [
            (
                # A single invalid file
                [Path("purelib") / "foo"],
                "Invalid binary wheel, found the following shared library/libraries in"
                " purelib folder:\n\tfoo\nThe wheel has to be platlib compliant in "
                "order to be repaired by auditwheel.",
            ),
            (
                # Multiple invalid files
                [Path("purelib") / "foo", Path("purelib") / "bar"],
                "Invalid binary wheel, found the following shared library/libraries in"
                " purelib folder:\n\tfoo\n\tbar\nThe wheel has to be platlib compliant"
                " in order to be repaired by auditwheel.",
            ),
        ],
    )
    def test_finds_shared_library_in_purelib(
        self,
        filenames: list[Path],
        message: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entered_context = pretend.stub(iter_files=lambda: filenames)
        context = pretend.stub(
            __enter__=lambda: entered_context,
            __exit__=lambda *_: None,
        )

        monkeypatch.setattr(wheel_abi, "InGenericPkgCtx", pretend.stub(__call__=lambda _: context))
        monkeypatch.setattr(
            wheel_abi,
            "elf_is_python_extension",
            lambda fn, elf: (fn, elf),
        )
        monkeypatch.setattr(
            wheel_abi,
            "elf_file_filter",
            lambda fns: [(fn, pretend.stub()) for fn in fns],
        )

        with pytest.raises(RuntimeError) as exec_info:
            wheel_abi.get_wheel_elfdata(
                Libc.GLIBC,
                Architecture.x86_64,
                Path("/fakepath"),
                frozenset(),
            )

        assert exec_info.value.args == (message,)


def test_get_symbol_policies() -> None:
    policies = WheelPolicies(libc=Libc.GLIBC, arch=Architecture.x86_64)
    versioned_symbols = defaultdict(set, {"libc.so.6": {"GLIBC_2.2.5"}})
    external_versioned_symbols = {
        "libmvec.so.1": {
            "libc.so.6": {"GLIBC_2.2.5"},
            "libm.so.6": {"GLIBC_2.15", "GLIBC_2.2.5"},
        },
    }
    external_refs = {}
    for policy in policies:
        if policy.name in {
            "manylinux_2_5_x86_64",
            "manylinux_2_12_x86_64",
            "manylinux_2_17_x86_64",
        }:
            libs = {"libmvec.so.1": Path("/lib64/libmvec-2.28.so")}
        else:
            libs = {}
        blacklist = {}
        external_refs[policy.name] = ExternalReference(libs, blacklist, policy)
    symbol_policies = wheel_abi.get_symbol_policies(
        policies,
        versioned_symbols,
        external_versioned_symbols,
        external_refs,
    )
    max_policy = max(symbol_policy[0] for symbol_policy in symbol_policies)
    assert max_policy.name == "manylinux_2_17_x86_64"


@pytest.mark.parametrize("kind", ["resolved", "unresolved", "warning"])
def test_nonpy_elf_resolution(kind: str, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    liba_path = tmp_path / "liba.so"
    libb_path = tmp_path / "libb.so"
    liba_path.touch()
    libb_path.touch()
    platform = Platform("", 64, True, "EM_X86_64", Architecture.x86_64, None, None)
    libb = DynamicExecutable(
        interpreter=None,
        libc=None,
        path="libb.so",
        realpath=libb_path,
        platform=platform,
        needed=(),
        rpath=(),
        runpath=(),
        libraries={},
    )
    liba = DynamicExecutable(
        interpreter=None,
        libc=None,
        path="liba.so",
        realpath=liba_path,
        platform=platform,
        needed=("libb.so",),
        rpath=(),
        runpath=(),
        libraries={
            "libb.so": DynamicLibrary("libb.so", None, None),
        },
    )
    libraries = {
        "liba.so": DynamicLibrary("liba.so", liba.path, liba.realpath, liba.platform, liba.needed),
    }
    if kind == "resolved":
        libraries["libb.so"] = DynamicLibrary(
            "libb.so",
            libb.path,
            libb.realpath,
            libb.platform,
            libb.needed,
        )
    elif kind == "unresolved":
        libraries["libb.so"] = DynamicLibrary("libb.so", None, None)
    extension = DynamicExecutable(
        interpreter=None,
        libc=None,
        path="extension.so",
        realpath=Path("extension.so"),
        platform=platform,
        needed=("liba.so",),
        rpath=(),
        runpath=(),
        libraries=libraries,
    )
    pyelf_trees = {extension.realpath: extension}
    nonpy_elftrees = {liba.realpath: liba, libb.realpath: libb}
    wheel_abi._fixup_elf_trees(pyelf_trees, nonpy_elftrees)
    assert pyelf_trees == {extension.realpath: extension}
    if kind == "resolved":
        assert nonpy_elftrees != {liba.realpath: liba, libb.realpath: libb}
        assert nonpy_elftrees[liba.realpath].libraries["libb.so"].realpath == libb.realpath
    else:
        assert nonpy_elftrees == {liba.realpath: liba, libb.realpath: libb}
        assert nonpy_elftrees[liba.realpath].libraries["libb.so"].realpath is None
    if kind == "warning":
        assert len(caplog.records) == 1
    else:
        assert len(caplog.records) == 0


@pytest.mark.parametrize("kind", ["resolved", "unresolved", "warning"])
def test_nonpy_elf_resolution_transitive_needed(
    kind: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    liba_path = tmp_path / "liba.so"
    libb_path = tmp_path / "libb.so"
    libc_path = tmp_path / "libc.so"
    liba_path.touch()
    libb_path.touch()
    libc_path.touch()
    platform = Platform("", 64, True, "EM_X86_64", Architecture.x86_64, None, None)
    libc = DynamicExecutable(
        interpreter=None,
        libc=None,
        path="libc.so",
        realpath=libc_path,
        platform=platform,
        needed=(),
        rpath=(),
        runpath=(),
        libraries={},
    )
    libb = DynamicExecutable(
        interpreter=None,
        libc=None,
        path="libb.so",
        realpath=libb_path,
        platform=platform,
        needed=("libc.so",),
        rpath=(),
        runpath=(),
        libraries={
            "libc.so": DynamicLibrary("libc.so", None, None),
        },
    )
    liba = DynamicExecutable(
        interpreter=None,
        libc=None,
        path="liba.so",
        realpath=liba_path,
        platform=platform,
        needed=("libb.so",),
        rpath=(),
        runpath=(),
        libraries={
            "libb.so": DynamicLibrary("libb.so", None, None),
        },
    )
    libraries = {
        "liba.so": DynamicLibrary("liba.so", liba.path, liba.realpath, liba.platform, liba.needed),
    }
    if kind in {"resolved", "warning"}:
        libraries["libb.so"] = DynamicLibrary(
            "libb.so",
            libb.path,
            libb.realpath,
            libb.platform,
            libb.needed,
        )
        if kind == "resolved":
            libraries["libc.so"] = DynamicLibrary(
                "libc.so",
                libc.path,
                libc.realpath,
                libc.platform,
                libc.needed,
            )
    elif kind == "unresolved":
        libraries["libb.so"] = DynamicLibrary("libb.so", None, None)

    extension = DynamicExecutable(
        interpreter=None,
        libc=None,
        path="extension.so",
        realpath=Path("extension.so"),
        platform=platform,
        needed=("liba.so",),
        rpath=(),
        runpath=(),
        libraries=libraries,
    )
    pyelf_trees = {extension.realpath: extension}
    nonpy_elftrees = {liba.realpath: liba, libb.realpath: libb, libc.realpath: libc}
    wheel_abi._fixup_elf_trees(pyelf_trees, nonpy_elftrees)
    assert pyelf_trees == {extension.realpath: extension}
    if kind in {"resolved", "warning"}:
        assert nonpy_elftrees != {liba.realpath: liba, libb.realpath: libb, libc.realpath: libc}
        assert nonpy_elftrees[liba.realpath].libraries["libb.so"].realpath == libb.realpath
        if kind == "resolved":
            assert nonpy_elftrees[liba.realpath].libraries["libc.so"].realpath == libc.realpath
            assert nonpy_elftrees[libb.realpath].libraries["libc.so"].realpath == libc.realpath
        else:
            assert "libc.so" not in nonpy_elftrees[liba.realpath].libraries
            assert nonpy_elftrees[libb.realpath].libraries["libc.so"].realpath is None
    else:
        assert nonpy_elftrees == {liba.realpath: liba, libb.realpath: libb, libc.realpath: libc}
        assert nonpy_elftrees[liba.realpath].libraries["libb.so"].realpath is None
        assert "libc.so" not in nonpy_elftrees[liba.realpath].libraries
        assert nonpy_elftrees[libb.realpath].libraries["libc.so"].realpath is None
    if kind == "warning":
        assert len(caplog.records) == 2
    else:
        assert len(caplog.records) == 0
