from __future__ import annotations

import re
from pathlib import Path
from subprocess import CalledProcessError
from unittest.mock import call, patch

import pytest

from auditwheel.patcher import ElfPatcher, Patchelf


def test_elfpatcher_replace_needed_overlap(tmp_path):
    filename = tmp_path / "test.so"
    filename.touch()
    patcher = ElfPatcher("")
    patcher.remove_needed(filename, "removed")
    with pytest.raises(ValueError, match=re.escape("can't add replace_needed entry")):
        patcher.replace_needed(filename, ("removed", "replaced"))


def test_elfpatcher_remove_needed_overlap(tmp_path):
    filename = tmp_path / "test.so"
    filename.touch()
    patcher = ElfPatcher("")
    patcher.replace_needed(filename, ("original", "replaced"))
    with pytest.raises(ValueError, match=re.escape("can't remove")):
        patcher.remove_needed(filename, "original")
    with pytest.raises(ValueError, match=re.escape("can't remove")):
        patcher.remove_needed(filename, "replaced")


def test_elfpatcher_get_rpath_replaced(tmp_path):
    filename = tmp_path / "test.so"
    filename.touch()
    patcher = ElfPatcher("")
    patcher.set_rpath(filename, "new-rpath")
    assert patcher.get_rpath(filename) == "new-rpath"


def test_elfpatcher_get_rpath_removed(tmp_path):
    filename = tmp_path / "test.so"
    filename.touch()
    patcher = ElfPatcher("")
    patcher.clear_rpath(filename)
    assert patcher.get_rpath(filename) == ""


def test_elfpatcher_update_elf_path(tmp_path):
    filename1 = tmp_path / "test1.so"
    filename1.touch()
    filename2 = tmp_path / "test2.so"
    filename2.touch()
    patcher = ElfPatcher("")
    patcher.clear_rpath(filename1)
    patcher.update_elf_path(filename1, filename2)
    assert len(patcher._updates) == 1
    key, value = patcher._updates.popitem()
    assert Path(key).samefile(filename2)
    assert value.clear_rpath is True


def test_elfpatcher_update_elf_path_noop(tmp_path):
    filename1 = tmp_path / "test1.so"
    filename1.touch()
    filename2 = tmp_path / "test2.so"
    filename2.touch()
    patcher = ElfPatcher("")
    patcher.update_elf_path(filename1, filename2)
    assert len(patcher._updates) == 0


@patch("auditwheel.patcher.which")
def test_patchelf_unavailable(which):
    which.return_value = False
    with pytest.raises(ValueError, match="Cannot find required utility"):
        Patchelf()


@patch("auditwheel.patcher.which")
@patch("auditwheel.patcher.check_output")
def test_patchelf_check_output_fail(check_output, which):
    which.return_value = True
    check_output.side_effect = CalledProcessError(1, "patchelf --version")
    with pytest.raises(ValueError, match="Could not call"):
        Patchelf()


@patch("auditwheel.patcher.which")
@patch("auditwheel.patcher.check_output")
@pytest.mark.parametrize("version", ["0.14", "0.14.1", "0.15"])
def test_patchelf_version_check(check_output, which, version):
    which.return_value = "patchelf"
    check_output.return_value.decode.return_value = f"patchelf {version}"
    Patchelf()


@patch("auditwheel.patcher.which")
@patch("auditwheel.patcher.check_output")
@pytest.mark.parametrize("version", ["0.13.99", "0.13", "0.9", "0.1"])
def test_patchelf_version_check_fail(check_output, which, version):
    which.return_value = True
    check_output.return_value.decode.return_value = f"patchelf {version}"
    with pytest.raises(ValueError, match=f"patchelf {version} found"):
        Patchelf()


@patch("auditwheel.patcher._verify_patchelf")
@patch("auditwheel.patcher.check_output")
@patch("auditwheel.patcher.check_call")
class TestPatchElf:
    """Validate that patchelf is invoked with the correct arguments."""

    def test_replace_needed_one(self, check_call, _0, _1, tmp_path):  # noqa: PT019
        patcher = Patchelf()
        patcher._patchelf_path = "patchelf"
        filename = tmp_path / "test.so"
        filename.touch()
        filename_key = filename.resolve(strict=True)
        soname_old = "TEST_OLD"
        soname_new = "TEST_NEW"
        patcher.replace_needed(filename, (soname_old, soname_new))
        patcher.apply_updates()
        check_call.assert_called_once_with(
            ["patchelf", "--replace-needed", soname_old, soname_new, filename_key],
        )

    def test_replace_needed_multiple(self, check_call, _0, _1, tmp_path):  # noqa: PT019
        patcher = Patchelf()
        patcher._patchelf_path = "patchelf"
        filename = tmp_path / "test.so"
        filename.touch()
        filename_key = filename.resolve(strict=True)
        replacements = [
            ("TEST_OLD1", "TEST_NEW1"),
            ("TEST_OLD2", "TEST_NEW2"),
        ]
        patcher.replace_needed(filename, *replacements)
        patcher.apply_updates()
        check_call.assert_called_once_with(
            [
                "patchelf",
                "--replace-needed",
                *replacements[0],
                "--replace-needed",
                *replacements[1],
                filename_key,
            ],
        )

    def test_set_soname(self, check_call, _0, _1, tmp_path):  # noqa: PT019
        patcher = Patchelf()
        patcher._patchelf_path = "patchelf"
        filename = tmp_path / "test.so"
        filename.touch()
        filename_key = filename.resolve(strict=True)
        soname_new = "TEST_NEW"
        patcher.set_soname(filename, soname_new)
        patcher.apply_updates()
        check_call.assert_called_once_with(
            ["patchelf", "--set-soname", soname_new, filename_key],
        )

    @pytest.mark.parametrize("platform", ["android_24_x86_64", "manylinux_2_26_x86_64"])
    def test_set_rpath(self, check_call, _0, _1, platform, tmp_path):  # noqa: PT019
        patcher = Patchelf(platform)
        patcher._patchelf_path = "patchelf"
        filename = tmp_path / "test.so"
        filename.touch()
        filename_key = filename.resolve(strict=True)
        patcher.set_rpath(filename, "$ORIGIN/.lib")
        patcher.apply_updates()
        check_call.assert_called_once_with(
            ["patchelf"]
            + ([] if platform.startswith("android") else ["--force-rpath"])
            + ["--set-rpath", "$ORIGIN/.lib", filename_key],
        )

    def test_set_rpath_android_old(self, check_call, _0, _1):  # noqa: PT019
        patcher = Patchelf("android_23_x86_64")
        filename = Path("test.so")
        with pytest.raises(ValueError, match="RUNPATH requires API level 24 or higher"):
            patcher.set_rpath(filename, "$ORIGIN/.lib")
        check_call.assert_not_called()

    def test_get_rpath(self, _0, check_output, _1, tmp_path):  # noqa: PT019
        patcher = Patchelf()
        patcher._patchelf_path = "patchelf"
        filename = tmp_path / "test.so"
        filename.touch()
        check_output.return_value = b"existing_rpath"
        result = patcher.get_rpath(filename)
        check_output_expected_args = [call(["patchelf", "--print-rpath", filename])]

        assert result == check_output.return_value.decode()
        assert check_output.call_args_list == check_output_expected_args

    def test_remove_needed(self, check_call, _0, _1, tmp_path):  # noqa: PT019
        patcher = Patchelf()
        patcher._patchelf_path = "patchelf"
        filename = tmp_path / "test.so"
        filename.touch()
        filename_key = filename.resolve(strict=True)
        soname_1 = "TEST_REM_1"
        soname_2 = "TEST_REM_2"
        patcher.remove_needed(filename, soname_1, soname_2)
        patcher.apply_updates()
        check_call.assert_called_once_with(
            [
                "patchelf",
                "--remove-needed",
                soname_1,
                "--remove-needed",
                soname_2,
                filename_key,
            ],
        )

    def test_clear_rpath(self, check_call, _0, _1, tmp_path):  # noqa: PT019
        patcher = Patchelf()
        patcher._patchelf_path = "patchelf"
        filename = tmp_path / "test.so"
        filename.touch()
        filename_key = filename.resolve(strict=True)
        patcher.clear_rpath(filename)
        patcher.apply_updates()
        check_call_expected_args = [
            call(["patchelf", "--remove-rpath", filename_key]),
        ]

        assert check_call.call_args_list == check_call_expected_args
