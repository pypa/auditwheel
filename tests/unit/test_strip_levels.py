from __future__ import annotations

from pathlib import Path
from unittest.mock import call, patch

import pytest

from auditwheel.repair import (
    StripLevel,
    _get_strip_args,
    process_symbols,
    strip_symbols,
)


class TestStripLevel:
    def test_strip_level_values(self):
        assert StripLevel.NONE.value == "none"
        assert StripLevel.DEBUG.value == "debug"
        assert StripLevel.UNNEEDED.value == "unneeded"
        assert StripLevel.ALL.value == "all"

    def test_strip_level_from_string(self):
        assert StripLevel("none") == StripLevel.NONE
        assert StripLevel("debug") == StripLevel.DEBUG
        assert StripLevel("unneeded") == StripLevel.UNNEEDED
        assert StripLevel("all") == StripLevel.ALL

    def test_strip_level_invalid_value(self):
        with pytest.raises(ValueError, match="'invalid' is not a valid StripLevel"):
            StripLevel("invalid")


class TestGetStripArgs:
    def test_none(self):
        assert _get_strip_args(StripLevel.NONE) == []

    def test_debug(self):
        assert _get_strip_args(StripLevel.DEBUG) == ["-g"]

    def test_unneeded(self):
        assert _get_strip_args(StripLevel.UNNEEDED) == ["--strip-unneeded"]

    def test_all(self):
        assert _get_strip_args(StripLevel.ALL) == ["-s"]


@patch("auditwheel.repair.check_call")
class TestProcessSymbols:
    def test_none_level_does_not_strip(self, mock_check_call):
        process_symbols([Path("lib1.so"), Path("lib2.so")], StripLevel.NONE)
        mock_check_call.assert_not_called()

    def test_empty_libraries_does_not_strip(self, mock_check_call):
        process_symbols([], StripLevel.ALL)
        mock_check_call.assert_not_called()

    def test_debug_level(self, mock_check_call):
        process_symbols([Path("lib1.so"), Path("lib2.so")], StripLevel.DEBUG)
        mock_check_call.assert_has_calls([
            call(["strip", "-g", "lib1.so"]),
            call(["strip", "-g", "lib2.so"]),
        ])

    def test_unneeded_level(self, mock_check_call):
        process_symbols([Path("lib1.so")], StripLevel.UNNEEDED)
        mock_check_call.assert_called_once_with(["strip", "--strip-unneeded", "lib1.so"])

    def test_all_level(self, mock_check_call):
        process_symbols([Path("lib1.so")], StripLevel.ALL)
        mock_check_call.assert_called_once_with(["strip", "-s", "lib1.so"])


@patch("auditwheel.repair.check_call")
class TestStripSymbolsBackwardCompatibility:
    def test_strip_symbols_uses_all_level(self, mock_check_call):
        strip_symbols([Path("lib1.so"), Path("lib2.so")])
        mock_check_call.assert_has_calls([
            call(["strip", "-s", "lib1.so"]),
            call(["strip", "-s", "lib2.so"]),
        ])
