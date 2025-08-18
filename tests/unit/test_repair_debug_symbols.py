from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import call, patch

import pytest

from auditwheel.repair import (
    StripLevel,
    _collect_debug_symbols,
    _get_strip_args,
    process_symbols,
    strip_symbols,
)


class TestStripLevel:
    """Test the StripLevel enum."""

    def test_strip_level_values(self):
        """Test that StripLevel enum has correct values."""
        assert StripLevel.NONE.value == "none"
        assert StripLevel.DEBUG.value == "debug"
        assert StripLevel.UNNEEDED.value == "unneeded"
        assert StripLevel.ALL.value == "all"

    def test_strip_level_from_string(self):
        """Test creating StripLevel from string values."""
        assert StripLevel("none") == StripLevel.NONE
        assert StripLevel("debug") == StripLevel.DEBUG
        assert StripLevel("unneeded") == StripLevel.UNNEEDED
        assert StripLevel("all") == StripLevel.ALL

    def test_strip_level_invalid_value(self):
        """Test that invalid values raise ValueError."""
        with pytest.raises(ValueError, match="'invalid' is not a valid StripLevel"):
            StripLevel("invalid")


class TestGetStripArgs:
    """Test the _get_strip_args function."""

    def test_get_strip_args_none(self):
        """Test strip args for NONE level."""
        args = _get_strip_args(StripLevel.NONE)
        assert args == []

    def test_get_strip_args_debug(self):
        """Test strip args for DEBUG level."""
        args = _get_strip_args(StripLevel.DEBUG)
        assert args == ["-g"]

    def test_get_strip_args_unneeded(self):
        """Test strip args for UNNEEDED level."""
        args = _get_strip_args(StripLevel.UNNEEDED)
        assert args == ["--strip-unneeded"]

    def test_get_strip_args_all(self):
        """Test strip args for ALL level."""
        args = _get_strip_args(StripLevel.ALL)
        assert args == ["-s"]


@patch("auditwheel.repair.check_call")
class TestProcessSymbols:
    """Test the process_symbols function."""

    def test_process_symbols_none_level(self, mock_check_call):
        """Test that NONE level doesn't call strip."""
        libraries = [Path("lib1.so"), Path("lib2.so")]
        process_symbols(libraries, StripLevel.NONE)
        mock_check_call.assert_not_called()

    def test_process_symbols_debug_level(self, mock_check_call):
        """Test that DEBUG level calls strip with -g."""
        libraries = [Path("lib1.so"), Path("lib2.so")]
        process_symbols(libraries, StripLevel.DEBUG)

        expected_calls = [
            call(["strip", "-g", "lib1.so"]),
            call(["strip", "-g", "lib2.so"]),
        ]
        mock_check_call.assert_has_calls(expected_calls)

    def test_process_symbols_unneeded_level(self, mock_check_call):
        """Test that UNNEEDED level calls strip with --strip-unneeded."""
        libraries = [Path("lib1.so")]
        process_symbols(libraries, StripLevel.UNNEEDED)

        mock_check_call.assert_called_once_with(
            ["strip", "--strip-unneeded", "lib1.so"]
        )

    def test_process_symbols_all_level(self, mock_check_call):
        """Test that ALL level calls strip with -s."""
        libraries = [Path("lib1.so")]
        process_symbols(libraries, StripLevel.ALL)

        mock_check_call.assert_called_once_with(["strip", "-s", "lib1.so"])

    def test_process_symbols_empty_libraries(self, mock_check_call):
        """Test that empty library list doesn't call strip."""
        process_symbols([], StripLevel.ALL)
        mock_check_call.assert_not_called()

    @patch("auditwheel.repair._collect_debug_symbols")
    def test_process_symbols_with_debug_collection(self, mock_collect, mock_check_call):
        """Test that debug symbols are collected when requested."""
        libraries = [Path("lib1.so")]
        debug_zip = Path("debug.zip")

        process_symbols(
            libraries,
            StripLevel.DEBUG,
            collect_debug_symbols=True,
            debug_symbols_zip=debug_zip,
        )

        mock_collect.assert_called_once_with(libraries, debug_zip)
        mock_check_call.assert_called_once_with(["strip", "-g", "lib1.so"])


@patch("auditwheel.repair.check_call")
class TestCollectDebugSymbols:
    """Test the _collect_debug_symbols function."""

    @patch("auditwheel.repair.zipfile.ZipFile")
    @patch("auditwheel.repair.tempfile.TemporaryDirectory")
    def test_collect_debug_symbols_success(
        self, mock_tempdir, mock_zipfile, mock_check_call
    ):
        """Test successful debug symbol collection."""
        # Setup mocks
        temp_path = Path("/tmp/test")
        mock_tempdir.return_value.__enter__.return_value = str(temp_path)

        mock_zip_instance = mock_zipfile.return_value.__enter__.return_value

        libraries = [Path("lib1.so"), Path("lib2.so")]
        debug_zip = Path("debug.zip")

        _collect_debug_symbols(libraries, debug_zip)

        # Verify objcopy calls for each library
        expected_objcopy_calls = [
            call(
                [
                    "objcopy",
                    "--only-keep-debug",
                    "lib1.so",
                    str(temp_path / "lib1.so.debug"),
                ]
            ),
            call(
                [
                    "objcopy",
                    f"--add-gnu-debuglink={temp_path / 'lib1.so.debug'}",
                    "lib1.so",
                ]
            ),
            call(
                [
                    "objcopy",
                    "--only-keep-debug",
                    "lib2.so",
                    str(temp_path / "lib2.so.debug"),
                ]
            ),
            call(
                [
                    "objcopy",
                    f"--add-gnu-debuglink={temp_path / 'lib2.so.debug'}",
                    "lib2.so",
                ]
            ),
        ]
        mock_check_call.assert_has_calls(expected_objcopy_calls)

        # Verify zip file creation
        mock_zipfile.assert_called_once_with(debug_zip, "w", zipfile.ZIP_DEFLATED)

        # Verify files added to zip
        expected_zip_calls = [
            call(temp_path / "lib1.so.debug", "lib1.so.debug"),
            call(temp_path / "lib2.so.debug", "lib2.so.debug"),
        ]
        mock_zip_instance.write.assert_has_calls(expected_zip_calls, any_order=True)

    @patch("auditwheel.repair.zipfile.ZipFile")
    @patch("auditwheel.repair.tempfile.TemporaryDirectory")
    def test_collect_debug_symbols_objcopy_failure(
        self, mock_tempdir, mock_zipfile, mock_check_call
    ):
        """Test handling objcopy failure."""
        temp_path = Path("/tmp/test")
        mock_tempdir.return_value.__enter__.return_value = str(temp_path)

        mock_zip_instance = mock_zipfile.return_value.__enter__.return_value

        # Make objcopy fail for first library
        def side_effect(args):
            if "lib1.so" in args[2]:
                msg = "objcopy failed"
                raise RuntimeError(msg)

        mock_check_call.side_effect = side_effect

        libraries = [Path("lib1.so"), Path("lib2.so")]
        debug_zip = Path("debug.zip")

        # Should not raise exception
        _collect_debug_symbols(libraries, debug_zip)

        # Only lib2.so should be in the zip
        mock_zip_instance.write.assert_called_once_with(
            temp_path / "lib2.so.debug", "lib2.so.debug"
        )

    def test_collect_debug_symbols_empty_libraries(self, mock_check_call):
        """Test with empty library list."""
        _collect_debug_symbols([], Path("debug.zip"))
        mock_check_call.assert_not_called()

    @patch("auditwheel.repair.zipfile.ZipFile")
    @patch("auditwheel.repair.tempfile.TemporaryDirectory")
    def test_collect_debug_symbols_relative_path(self, mock_tempdir, mock_zipfile):
        """Test that relative paths are handled correctly in zip archive."""
        temp_path = Path("/tmp/test")
        mock_tempdir.return_value.__enter__.return_value = str(temp_path)

        mock_zip_instance = mock_zipfile.return_value.__enter__.return_value

        libraries = [Path("./lib1.so")]  # Relative path
        debug_zip = Path("debug.zip")

        _collect_debug_symbols(libraries, debug_zip)

        # Should strip the "./" prefix in the zip archive
        mock_zip_instance.write.assert_called_once_with(
            temp_path / "lib1.so.debug", "lib1.so.debug"
        )


@patch("auditwheel.repair.check_call")
class TestStripSymbolsBackwardCompatibility:
    """Test the backward compatibility strip_symbols function."""

    def test_strip_symbols_calls_process_symbols(self, mock_check_call):
        """Test that strip_symbols calls process_symbols with ALL level."""
        libraries = [Path("lib1.so"), Path("lib2.so")]
        strip_symbols(libraries)

        expected_calls = [
            call(["strip", "-s", "lib1.so"]),
            call(["strip", "-s", "lib2.so"]),
        ]
        mock_check_call.assert_has_calls(expected_calls)
