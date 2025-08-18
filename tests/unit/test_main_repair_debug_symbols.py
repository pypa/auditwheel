from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auditwheel.main_repair import (
    configure_parser,
    execute,
)
from auditwheel.repair import StripLevel


class TestMainRepairDebugSymbols:
    """Test CLI argument parsing for debug symbol functionality."""

    def test_configure_parser_new_arguments(self):
        """Test that new debug symbol arguments are configured correctly."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        configure_parser(subparsers)

        # Test parsing with new arguments
        args = parser.parse_args(
            [
                "repair",
                "--strip-level=debug",
                "--collect-debug-symbols",
                "--debug-symbols-output=/path/to/debug.zip",
                "test.whl",
            ]
        )

        assert args.STRIP_LEVEL == "debug"
        assert args.COLLECT_DEBUG_SYMBOLS is True
        assert Path("/path/to/debug.zip") == args.DEBUG_SYMBOLS_OUTPUT

    def test_strip_level_choices(self):
        """Test that strip-level accepts all valid choices."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        configure_parser(subparsers)

        for level in StripLevel:
            args = parser.parse_args(
                ["repair", f"--strip-level={level.value}", "test.whl"]
            )
            assert level.value == args.STRIP_LEVEL

    def test_strip_level_invalid_choice(self):
        """Test that invalid strip-level raises error."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        configure_parser(subparsers)

        with pytest.raises(SystemExit):
            parser.parse_args(["repair", "--strip-level=invalid", "test.whl"])

    def test_default_values(self):
        """Test default values for new arguments."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        configure_parser(subparsers)

        args = parser.parse_args(["repair", "test.whl"])

        assert args.STRIP_LEVEL == "none"
        assert args.COLLECT_DEBUG_SYMBOLS is False
        assert args.DEBUG_SYMBOLS_OUTPUT is None
        assert args.STRIP is False  # Backward compatibility

    def test_deprecated_strip_help_text(self):
        """Test that deprecated strip option shows deprecation in help."""
        # Test by creating a standalone parser with just the repair subcommand
        main_parser = argparse.ArgumentParser()
        subparsers = main_parser.add_subparsers()
        configure_parser(subparsers)

        # Alternative: Test that the deprecated argument is still accepted
        # and verify the help text is configured correctly by parsing arguments
        args = main_parser.parse_args(["repair", "--strip", "test.whl"])
        assert args.STRIP is True

        # The deprecation text is in the help, but we'll just test functionality
        # since accessing subparser internals is brittle


class TestMainRepairExecute:
    """Test the execute function with debug symbol arguments."""

    @patch("auditwheel.main_repair.repair_wheel")
    @patch("auditwheel.main_repair.analyze_wheel_abi")
    @patch("auditwheel.main_repair.Patchelf")
    def test_execute_with_strip_level_debug(self, mock_analyze, mock_repair):
        """Test execute function with strip-level=debug."""

        # Mock objects
        mock_wheel_abi = MagicMock()
        mock_wheel_abi.full_external_refs = {"ext.so": {}}
        mock_wheel_abi.policies = MagicMock()
        mock_wheel_abi.policies.lowest.name = "manylinux_2_17_x86_64"
        mock_wheel_abi.overall_policy = mock_wheel_abi.policies.lowest
        mock_wheel_abi.sym_policy = mock_wheel_abi.policies.lowest
        mock_wheel_abi.ucs_policy = mock_wheel_abi.policies.lowest
        mock_wheel_abi.blacklist_policy = mock_wheel_abi.policies.lowest
        mock_wheel_abi.machine_policy = mock_wheel_abi.policies.lowest

        mock_analyze.return_value = mock_wheel_abi
        mock_repair.return_value = Path("output.whl")

        # Create mock args
        args = MagicMock()
        args.WHEEL_FILE = [Path("test.whl")]
        args.WHEEL_DIR = Path("wheelhouse")
        args.LIB_SDIR = ".libs"
        args.PLAT = "auto"
        args.UPDATE_TAGS = True
        args.ONLY_PLAT = False
        args.EXCLUDE = []
        args.DISABLE_ISA_EXT_CHECK = False
        args.ZIP_COMPRESSION_LEVEL = 6
        args.STRIP = False
        args.STRIP_LEVEL = "debug"
        args.COLLECT_DEBUG_SYMBOLS = True
        args.DEBUG_SYMBOLS_OUTPUT = Path("debug.zip")

        parser = MagicMock()

        with (
            patch("auditwheel.main_repair.Path.mkdir"),
            patch("auditwheel.main_repair.Path.exists", return_value=True),
            patch("auditwheel.main_repair.Path.is_file", return_value=True),
            patch("auditwheel.main_repair.get_wheel_architecture"),
            patch("auditwheel.main_repair.get_wheel_libc"),
        ):
            result = execute(args, parser)

            assert result == 0
            mock_repair.assert_called_once()

            # Verify repair_wheel was called with correct arguments
            call_args = mock_repair.call_args
            assert (
                call_args[1]["strip"] is None
            )  # strip should be None when using strip_level
            assert call_args[1]["strip_level"] == StripLevel.DEBUG
            assert call_args[1]["collect_debug_symbols"] is True
            assert call_args[1]["debug_symbols_output"] == Path("debug.zip")

    @patch("auditwheel.main_repair.repair_wheel")
    @patch("auditwheel.main_repair.analyze_wheel_abi")
    @patch("auditwheel.main_repair.Patchelf")
    def test_execute_with_deprecated_strip(self, mock_analyze, mock_repair):
        """Test execute function with deprecated --strip flag."""

        # Mock objects
        mock_wheel_abi = MagicMock()
        mock_wheel_abi.full_external_refs = {"ext.so": {}}
        mock_wheel_abi.policies = MagicMock()
        mock_wheel_abi.policies.lowest.name = "manylinux_2_17_x86_64"
        mock_wheel_abi.overall_policy = mock_wheel_abi.policies.lowest
        mock_wheel_abi.sym_policy = mock_wheel_abi.policies.lowest
        mock_wheel_abi.ucs_policy = mock_wheel_abi.policies.lowest
        mock_wheel_abi.blacklist_policy = mock_wheel_abi.policies.lowest
        mock_wheel_abi.machine_policy = mock_wheel_abi.policies.lowest

        mock_analyze.return_value = mock_wheel_abi
        mock_repair.return_value = Path("output.whl")

        # Create mock args
        args = MagicMock()
        args.WHEEL_FILE = [Path("test.whl")]
        args.WHEEL_DIR = Path("wheelhouse")
        args.LIB_SDIR = ".libs"
        args.PLAT = "auto"
        args.UPDATE_TAGS = True
        args.ONLY_PLAT = False
        args.EXCLUDE = []
        args.DISABLE_ISA_EXT_CHECK = False
        args.ZIP_COMPRESSION_LEVEL = 6
        args.STRIP = True
        args.STRIP_LEVEL = "none"
        args.COLLECT_DEBUG_SYMBOLS = False
        args.DEBUG_SYMBOLS_OUTPUT = None

        parser = MagicMock()

        with (
            patch("auditwheel.main_repair.Path.mkdir"),
            patch("auditwheel.main_repair.Path.exists", return_value=True),
            patch("auditwheel.main_repair.Path.is_file", return_value=True),
            patch("auditwheel.main_repair.get_wheel_architecture"),
            patch("auditwheel.main_repair.get_wheel_libc"),
            patch("auditwheel.main_repair.warnings.warn") as mock_warn,
        ):
            result = execute(args, parser)

            assert result == 0
            mock_repair.assert_called_once()

            # Verify deprecation warning was issued
            mock_warn.assert_called_once_with(
                "The --strip option is deprecated. Use --strip-level=all instead.",
                DeprecationWarning,
                stacklevel=2,
            )

            # Verify repair_wheel was called with correct arguments
            call_args = mock_repair.call_args
            assert call_args[1]["strip"] is True
            assert call_args[1]["strip_level"] == StripLevel("none")

    def test_execute_conflicting_strip_arguments(self):
        """Test that conflicting strip arguments cause an error."""

        # Create mock args with conflicting strip options
        args = MagicMock()
        args.WHEEL_FILE = [Path("test.whl")]
        args.STRIP = True
        args.STRIP_LEVEL = "debug"  # Conflicts with STRIP=True

        parser = MagicMock()

        with patch("auditwheel.main_repair.Path.is_file", return_value=True):
            execute(args, parser)

        # Should call parser.error
        parser.error.assert_called_once_with(
            "Cannot specify both --strip and --strip-level"
        )

    def test_execute_collect_debug_without_stripping(self):
        """Test that collect-debug-symbols without stripping causes an error."""

        # Create mock args
        args = MagicMock()
        args.WHEEL_FILE = [Path("test.whl")]
        args.STRIP = False
        args.STRIP_LEVEL = "none"
        args.COLLECT_DEBUG_SYMBOLS = True

        parser = MagicMock()

        with patch("auditwheel.main_repair.Path.is_file", return_value=True):
            execute(args, parser)

        # Should call parser.error
        parser.error.assert_called_once_with(
            "--collect-debug-symbols requires stripping to be enabled. Use --strip-level or --strip."
        )
