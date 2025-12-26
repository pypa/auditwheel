from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pretend
import pytest

from auditwheel import wheel_abi
from auditwheel.architecture import Architecture
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
