from __future__ import annotations

from pathlib import Path

import pretend
import pytest

from auditwheel import wheel_abi
from auditwheel.policy import WheelPolicies


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
        self, filenames: list[Path], message: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entered_context = pretend.stub(iter_files=lambda: filenames)
        context = pretend.stub(
            __enter__=lambda: entered_context, __exit__=lambda *_: None
        )
        InGenericPkgCtx = pretend.stub(__call__=lambda _: context)

        monkeypatch.setattr(wheel_abi, "InGenericPkgCtx", InGenericPkgCtx)
        monkeypatch.setattr(
            wheel_abi, "elf_is_python_extension", lambda fn, elf: (fn, elf)
        )
        monkeypatch.setattr(
            wheel_abi,
            "elf_file_filter",
            lambda fns: [(fn, pretend.stub()) for fn in fns],
        )
        wheel_policy = WheelPolicies()

        with pytest.raises(RuntimeError) as exec_info:
            wheel_abi.get_wheel_elfdata(wheel_policy, Path("/fakepath"), frozenset())

        assert exec_info.value.args == (message,)
