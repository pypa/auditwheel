import os

import pytest
import pretend
from auditwheel import wheel_abi


class TestGetWheelElfdata:
    @pytest.mark.parametrize(
        "filenames, message",
        [
            (
                # A single invalid file
                [os.sep.join(["purelib", "foo"])],
                "Invalid binary wheel, found the following shared library/libraries in purelib folder:\n\tfoo\nThe wheel has to be platlib compliant in order to be repaired by auditwheel.",
            ),
            (
                # Multiple invalid files
                [os.sep.join(["purelib", "foo"]), os.sep.join(["purelib", "bar"])],
                "Invalid binary wheel, found the following shared library/libraries in purelib folder:\n\tfoo\n\tbar\nThe wheel has to be platlib compliant in order to be repaired by auditwheel.",
            ),
        ],
    )
    def test_finds_shared_library_in_purelib(self, filenames, message, monkeypatch):
        entered_context = pretend.stub(iter_files=lambda: filenames)
        context = pretend.stub(
            __enter__=lambda: entered_context, __exit__=lambda *a: None
        )
        InGenericPkgCtx = pretend.stub(__call__=lambda a: context)

        monkeypatch.setattr(wheel_abi, "InGenericPkgCtx", InGenericPkgCtx)
        monkeypatch.setattr(
            wheel_abi, "elf_is_python_extension", lambda fn, elf: (fn, elf)
        )
        monkeypatch.setattr(
            wheel_abi,
            "elf_file_filter",
            lambda fns: [(fn, pretend.stub()) for fn in fns],
        )

        with pytest.raises(RuntimeError) as exec_info:
            wheel_abi.get_wheel_elfdata("/fakepath")

        assert exec_info.value.args == (message,)
