from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pretend
import pytest

from auditwheel import wheel_abi
from auditwheel.architecture import Architecture
from auditwheel.lddtree import DynamicExecutable, Platform
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

    def test_filters_internal_nonpy_refs_for_repair(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeCtx:
            path = Path("/wheel")

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def iter_files(self):
                return [Path("pkg/ext.so"), Path("pkg/libinner.so")]

        platform = Platform(
            "",
            64,
            True,
            "EM_X86_64",
            Architecture.x86_64,
            None,
            None,
        )
        ext_tree = DynamicExecutable(
            libc=Libc.GLIBC,
            interpreter=None,
            path="pkg/ext.so",
            realpath=Path("/wheel/pkg/ext.so"),
            platform=platform,
            needed=("libinner.so",),
            rpath=(),
            runpath=(),
            libraries={},
        )
        inner_tree = DynamicExecutable(
            libc=Libc.GLIBC,
            interpreter=None,
            path="pkg/libinner.so",
            realpath=Path("/wheel/pkg/libinner.so"),
            platform=platform,
            needed=(),
            rpath=(),
            runpath=(),
            libraries={},
        )

        external_ref = {
            "manylinux_2_17_x86_64": ExternalReference(
                {
                    "libinner.so": None,
                    "libc.so.6": Path("/lib64/libc.so.6"),
                },
                {},
                pretend.stub(priority=80),
            ),
        }
        fake_policies = pretend.stub(
            lddtree_external_references=lambda _elftree, _wheel_path: external_ref,
        )

        monkeypatch.setattr(
            wheel_abi,
            "InGenericPkgCtx",
            pretend.stub(__call__=lambda _wheel: FakeCtx()),
        )
        monkeypatch.setattr(
            wheel_abi,
            "elf_file_filter",
            lambda _files: [
                (Path("pkg/ext.so"), pretend.stub()),
                (Path("pkg/libinner.so"), pretend.stub()),
            ],
        )
        monkeypatch.setattr(
            wheel_abi,
            "ldd",
            lambda fn, **_kwargs: {
                Path("pkg/ext.so"): ext_tree,
                Path("pkg/libinner.so"): inner_tree,
            }[fn],
        )
        monkeypatch.setattr(
            wheel_abi,
            "elf_find_versioned_symbols",
            lambda _elf: [],
        )
        monkeypatch.setattr(
            wheel_abi,
            "elf_is_python_extension",
            lambda fn, _elf: (fn == Path("pkg/ext.so"), 3),
        )
        monkeypatch.setattr(
            wheel_abi,
            "elf_references_pyfpe_jbuf",
            lambda _elf: False,
        )
        monkeypatch.setattr(
            wheel_abi,
            "WheelPolicies",
            lambda **_kwargs: fake_policies,
        )

        wheel_abi.get_wheel_elfdata.cache_clear()
        result = wheel_abi.get_wheel_elfdata(
            Libc.GLIBC,
            Architecture.x86_64,
            Path("/fakepath"),
            frozenset(),
        )

        assert Path("pkg/ext.so") in result.full_external_refs
        assert Path("pkg/libinner.so") in result.full_external_refs
        assert Path("pkg/libinner.so") in result.repair_external_refs
        assert result.repair_external_refs[Path("pkg/libinner.so")][
            "manylinux_2_17_x86_64"
        ].libs == {
            "libc.so.6": Path("/lib64/libc.so.6"),
        }
        assert Path("pkg/libinner.so") not in result.full_elftree

    def test_keeps_nonpy_roots_in_analysis(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeCtx:
            path = Path("/wheel")

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def iter_files(self):
                return [Path("pkg/tool.so")]

        platform = Platform(
            "",
            64,
            True,
            "EM_X86_64",
            Architecture.x86_64,
            None,
            None,
        )
        tree = DynamicExecutable(
            libc=Libc.GLIBC,
            interpreter=None,
            path="pkg/tool.so",
            realpath=Path("/wheel/pkg/tool.so"),
            platform=platform,
            needed=(),
            rpath=(),
            runpath=(),
            libraries={},
        )

        external_ref = {
            "manylinux_2_17_x86_64": ExternalReference(
                {},
                {"libc.so.6": ["bad_symbol"]},
                pretend.stub(priority=80),
            ),
        }
        fake_policies = pretend.stub(
            lddtree_external_references=lambda _elftree, _wheel_path: external_ref,
        )

        monkeypatch.setattr(
            wheel_abi,
            "InGenericPkgCtx",
            pretend.stub(__call__=lambda _wheel: FakeCtx()),
        )
        monkeypatch.setattr(
            wheel_abi,
            "elf_file_filter",
            lambda _files: [(Path("pkg/tool.so"), pretend.stub())],
        )
        monkeypatch.setattr(wheel_abi, "ldd", lambda _fn, **_kwargs: tree)
        monkeypatch.setattr(wheel_abi, "elf_find_versioned_symbols", lambda _elf: [])
        monkeypatch.setattr(wheel_abi, "elf_is_python_extension", lambda *_args: (False, 3))
        monkeypatch.setattr(wheel_abi, "elf_references_pyfpe_jbuf", lambda _elf: False)
        monkeypatch.setattr(
            wheel_abi,
            "WheelPolicies",
            lambda **_kwargs: fake_policies,
        )

        wheel_abi.get_wheel_elfdata.cache_clear()
        result = wheel_abi.get_wheel_elfdata(
            Libc.GLIBC,
            Architecture.x86_64,
            Path("/fakepath"),
            frozenset(),
        )

        assert Path("pkg/tool.so") in result.full_elftree
        assert Path("pkg/tool.so") in result.repair_external_refs


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
