from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auditwheel.main_repair import configure_parser, execute
from auditwheel.repair import StripLevel


class TestStripLevelArgument:
    def test_default_values(self):
        parser = argparse.ArgumentParser()
        configure_parser(parser.add_subparsers())
        args = parser.parse_args(["repair", "test.whl"])
        assert args.STRIP_LEVEL == "none"
        assert args.STRIP is False

    def test_strip_level_choices(self):
        parser = argparse.ArgumentParser()
        configure_parser(parser.add_subparsers())
        for level in StripLevel:
            args = parser.parse_args(["repair", f"--strip-level={level.value}", "test.whl"])
            assert args.STRIP_LEVEL == level.value

    def test_strip_level_invalid_choice(self):
        parser = argparse.ArgumentParser()
        configure_parser(parser.add_subparsers())
        with pytest.raises(SystemExit):
            parser.parse_args(["repair", "--strip-level=invalid", "test.whl"])

    def test_deprecated_strip_still_accepted(self):
        parser = argparse.ArgumentParser()
        configure_parser(parser.add_subparsers())
        args = parser.parse_args(["repair", "--strip", "test.whl"])
        assert args.STRIP is True


class TestStripLevelExecute:
    def _make_wheel_abi_mock(self):
        mock_wheel_abi = MagicMock()
        mock_wheel_abi.full_external_refs = {}
        mock_wheel_abi.policies = MagicMock()

        # Create a single policy mock that supports rich comparison (Python 3.14+
        # raises TypeError for MagicMock > MagicMock without explicit __gt__).
        mock_policy = MagicMock()
        mock_policy.name = "manylinux_2_17_x86_64"
        type(mock_policy).__gt__ = lambda self, other: False
        type(mock_policy).__lt__ = lambda self, other: False

        mock_wheel_abi.policies.lowest = mock_policy
        mock_wheel_abi.policies.get_policy_by_name = MagicMock(return_value=mock_policy)
        mock_wheel_abi.overall_policy = mock_policy
        mock_wheel_abi.sym_policy = mock_policy
        mock_wheel_abi.ucs_policy = mock_policy
        mock_wheel_abi.blacklist_policy = mock_policy
        mock_wheel_abi.machine_policy = mock_policy
        return mock_wheel_abi

    def _make_args(self, **kwargs):
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
        args.STRIP_LEVEL = "none"
        args.ALLOW_PURE_PY_WHEEL = False
        for k, v in kwargs.items():
            setattr(args, k, v)
        return args

    # repair_wheel and analyze_wheel_abi are lazily imported inside execute(),
    # so they must be patched at their source modules, not at auditwheel.main_repair.
    @patch("auditwheel.repair.repair_wheel")
    @patch("auditwheel.wheel_abi.analyze_wheel_abi")
    @patch("auditwheel.main_repair.Patchelf")
    def test_strip_level_debug_passed_to_repair_wheel(
        self, _mock_patchelf, mock_analyze, mock_repair
    ):
        mock_analyze.return_value = self._make_wheel_abi_mock()
        mock_repair.return_value = Path("output.whl")
        args = self._make_args(STRIP_LEVEL="debug")

        with (
            patch("auditwheel.main_repair.Path.mkdir"),
            patch("auditwheel.main_repair.Path.exists", return_value=True),
            patch("auditwheel.main_repair.Path.is_file", return_value=True),
            patch("auditwheel.main_repair.get_wheel_architecture"),
            patch("auditwheel.main_repair.get_wheel_libc"),
        ):
            result = execute(args, MagicMock())

        assert result == 0
        call_kwargs = mock_repair.call_args[1]
        assert call_kwargs["strip_level"] == StripLevel.DEBUG
        assert "strip" not in call_kwargs  # deprecated param not forwarded

    @patch("auditwheel.repair.repair_wheel")
    @patch("auditwheel.wheel_abi.analyze_wheel_abi")
    @patch("auditwheel.main_repair.Patchelf")
    def test_deprecated_strip_resolves_to_strip_level_all(
        self, _mock_patchelf, mock_analyze, mock_repair
    ):
        """--strip is deprecated; it resolves to strip_level=ALL before the loop."""
        mock_analyze.return_value = self._make_wheel_abi_mock()
        mock_repair.return_value = Path("output.whl")
        args = self._make_args(STRIP=True)

        with (
            patch("auditwheel.main_repair.Path.mkdir"),
            patch("auditwheel.main_repair.Path.exists", return_value=True),
            patch("auditwheel.main_repair.Path.is_file", return_value=True),
            patch("auditwheel.main_repair.get_wheel_architecture"),
            patch("auditwheel.main_repair.get_wheel_libc"),
            patch("auditwheel.main_repair.warnings.warn") as mock_warn,
        ):
            result = execute(args, MagicMock())

        assert result == 0
        mock_warn.assert_called_once_with(
            "The --strip option is deprecated. Use --strip-level=all instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        call_kwargs = mock_repair.call_args[1]
        assert call_kwargs["strip_level"] == StripLevel.ALL
        assert "strip" not in call_kwargs

    def test_conflicting_strip_and_strip_level_errors(self):
        args = self._make_args(STRIP=True, STRIP_LEVEL="debug")
        parser = MagicMock()
        # parser.error must halt execution (as argparse does) so subsequent code
        # doesn't run after the conflict is detected.
        parser.error.side_effect = SystemExit(2)
        with pytest.raises(SystemExit):
            execute(args, parser)
        parser.error.assert_called_once_with("Cannot specify both --strip and --strip-level")
