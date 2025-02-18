from __future__ import annotations

from pathlib import Path
from subprocess import CalledProcessError
from unittest.mock import call, patch

import pytest

from auditwheel.patcher import Patchelf


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
    which.return_value = True
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
    """ "Validate that patchelf is invoked with the correct arguments."""

    def test_replace_needed_one(self, check_call, _0, _1):  # noqa: PT019
        patcher = Patchelf()
        filename = Path("test.so")
        soname_old = "TEST_OLD"
        soname_new = "TEST_NEW"
        patcher.replace_needed(filename, (soname_old, soname_new))
        check_call.assert_called_once_with(
            ["patchelf", "--replace-needed", soname_old, soname_new, filename]
        )

    def test_replace_needed_multple(self, check_call, _0, _1):  # noqa: PT019
        patcher = Patchelf()
        filename = Path("test.so")
        replacements = [
            ("TEST_OLD1", "TEST_NEW1"),
            ("TEST_OLD2", "TEST_NEW2"),
        ]
        patcher.replace_needed(filename, *replacements)
        check_call.assert_called_once_with(
            [
                "patchelf",
                "--replace-needed",
                *replacements[0],
                "--replace-needed",
                *replacements[1],
                filename,
            ]
        )

    def test_set_soname(self, check_call, _0, _1):  # noqa: PT019
        patcher = Patchelf()
        filename = Path("test.so")
        soname_new = "TEST_NEW"
        patcher.set_soname(filename, soname_new)
        check_call.assert_called_once_with(
            ["patchelf", "--set-soname", soname_new, filename]
        )

    def test_set_rpath(self, check_call, _0, _1):  # noqa: PT019
        patcher = Patchelf()
        filename = Path("test.so")
        patcher.set_rpath(filename, "$ORIGIN/.lib")
        check_call_expected_args = [
            call(["patchelf", "--remove-rpath", filename]),
            call(
                ["patchelf", "--force-rpath", "--set-rpath", "$ORIGIN/.lib", filename]
            ),
        ]

        assert check_call.call_args_list == check_call_expected_args

    def test_get_rpath(self, _0, check_output, _1):  # noqa: PT019
        patcher = Patchelf()
        filename = Path("test.so")
        check_output.return_value = b"existing_rpath"
        result = patcher.get_rpath(filename)
        check_output_expected_args = [call(["patchelf", "--print-rpath", filename])]

        assert result == check_output.return_value.decode()
        assert check_output.call_args_list == check_output_expected_args
