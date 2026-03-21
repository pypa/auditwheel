from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auditwheel.repair import StripLevel, repair_wheel


class TestRepairWheelStripLevels:
    """Tests for repair_wheel strip level behaviour."""

    def _make_wheel_abi(self, libs=None):
        mock = MagicMock()
        mock.full_external_refs = {
            Path("ext.so"): {
                "manylinux_2_17_x86_64": MagicMock(libs=libs or {})
            }
        }
        return mock

    @patch("auditwheel.repair.process_symbols")
    @patch("auditwheel.repair.InWheelCtx")
    def test_strip_level_none_does_not_call_process_symbols(
        self, mock_ctx_cls, mock_process
    ):
        mock_ctx = MagicMock()
        mock_ctx_cls.return_value.__enter__.return_value = mock_ctx
        mock_ctx.out_wheel = Path("output.whl")
        mock_ctx.name = Path("wheel_name")

        with tempfile.TemporaryDirectory() as d:
            repair_wheel(
                wheel_abi=self._make_wheel_abi(),
                wheel_path=Path("pkg-1.0-py3-none-linux_x86_64.whl"),
                abis=["manylinux_2_17_x86_64"],
                lib_sdir=".libs",
                out_dir=Path(d),
                update_tags=False,
                patcher=MagicMock(),
                strip_level=StripLevel.NONE,
            )

        mock_process.assert_not_called()

    @patch("auditwheel.repair.process_symbols")
    @patch("auditwheel.repair.InWheelCtx")
    def test_strip_level_debug_calls_process_symbols(self, mock_ctx_cls, mock_process):
        mock_ctx = MagicMock()
        mock_ctx_cls.return_value.__enter__.return_value = mock_ctx
        mock_ctx.out_wheel = Path("output.whl")
        mock_ctx.name = Path("wheel_name")

        with tempfile.TemporaryDirectory() as d:
            repair_wheel(
                wheel_abi=self._make_wheel_abi(),
                wheel_path=Path("pkg-1.0-py3-none-linux_x86_64.whl"),
                abis=["manylinux_2_17_x86_64"],
                lib_sdir=".libs",
                out_dir=Path(d),
                update_tags=False,
                patcher=MagicMock(),
                strip_level=StripLevel.DEBUG,
            )

        mock_process.assert_called_once()
        libs, level = mock_process.call_args[0]
        assert level == StripLevel.DEBUG
        assert Path("ext.so") in list(libs)

    @patch("auditwheel.repair.process_symbols")
    @patch("auditwheel.repair.InWheelCtx")
    def test_strip_true_maps_to_strip_level_all(self, mock_ctx_cls, mock_process):
        """Backward compatibility: strip=True behaves like strip_level=ALL."""
        mock_ctx = MagicMock()
        mock_ctx_cls.return_value.__enter__.return_value = mock_ctx
        mock_ctx.out_wheel = Path("output.whl")
        mock_ctx.name = Path("wheel_name")

        with tempfile.TemporaryDirectory() as d:
            repair_wheel(
                wheel_abi=self._make_wheel_abi(),
                wheel_path=Path("pkg-1.0-py3-none-linux_x86_64.whl"),
                abis=["manylinux_2_17_x86_64"],
                lib_sdir=".libs",
                out_dir=Path(d),
                update_tags=False,
                patcher=MagicMock(),
                strip=True,
            )

        mock_process.assert_called_once()
        _, level = mock_process.call_args[0]
        assert level == StripLevel.ALL

    def test_conflicting_strip_and_strip_level_raises(self):
        mock_abi = MagicMock()
        mock_abi.full_external_refs = {}
        with pytest.raises(ValueError, match="Cannot specify both"):
            repair_wheel(
                wheel_abi=mock_abi,
                wheel_path=Path("pkg-1.0-py3-none-linux_x86_64.whl"),
                abis=["manylinux_2_17_x86_64"],
                lib_sdir=".libs",
                out_dir=Path("/tmp"),
                update_tags=False,
                patcher=MagicMock(),
                strip=True,
                strip_level=StripLevel.DEBUG,
            )

    def test_pure_wheel_returns_none(self):
        mock_abi = MagicMock()
        mock_abi.full_external_refs = {}
        result = repair_wheel(
            wheel_abi=mock_abi,
            wheel_path=Path("pkg-1.0-py3-none-linux_x86_64.whl"),
            abis=["manylinux_2_17_x86_64"],
            lib_sdir=".libs",
            out_dir=Path("/tmp"),
            update_tags=False,
            patcher=MagicMock(),
            strip_level=StripLevel.DEBUG,
        )
        assert result is None
