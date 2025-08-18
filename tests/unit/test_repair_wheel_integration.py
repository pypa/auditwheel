from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from auditwheel.repair import StripLevel, repair_wheel


class TestRepairWheelIntegration:
    """Integration tests for repair_wheel with debug symbol functionality."""

    @patch("auditwheel.repair.process_symbols")
    @patch("auditwheel.repair.InWheelCtx")
    def test_repair_wheel_with_strip_level_debug(
        self, mock_wheel_ctx, mock_process_symbols
    ):
        """Test repair_wheel with strip_level=DEBUG."""
        # Mock wheel context
        mock_ctx = MagicMock()
        mock_wheel_ctx.return_value.__enter__.return_value = mock_ctx
        mock_ctx.out_wheel = Path("output.whl")
        mock_ctx.name = Path("wheel_name")

        # Mock wheel ABI
        mock_wheel_abi = MagicMock()
        mock_wheel_abi.full_external_refs = {
            Path("ext.so"): {"manylinux_2_17_x86_64": MagicMock(libs={})}
        }

        # Mock patcher
        mock_patcher = MagicMock()

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)

            result = repair_wheel(
                wheel_abi=mock_wheel_abi,
                wheel_path=Path("package-1.0-py3-none-linux_x86_64.whl"),
                abis=["manylinux_2_17_x86_64"],
                lib_sdir=".libs",
                out_dir=out_dir,
                update_tags=False,
                patcher=mock_patcher,
                strip_level=StripLevel.DEBUG,
                collect_debug_symbols=False,
                debug_symbols_output=None,
            )

            # Should call process_symbols with correct arguments
            mock_process_symbols.assert_called_once()
            args, kwargs = mock_process_symbols.call_args
            libraries, strip_level, collect_debug_symbols, debug_symbols_zip = args

            assert list(libraries) == [Path("ext.so")]
            assert strip_level == StripLevel.DEBUG
            assert collect_debug_symbols is False
            assert debug_symbols_zip is None

            assert result == Path("output.whl")

    @patch("auditwheel.repair.process_symbols")
    @patch("auditwheel.repair.InWheelCtx")
    @patch("auditwheel.repair.WHEEL_INFO_RE")
    def test_repair_wheel_with_debug_collection(
        self, mock_wheel_info, mock_wheel_ctx, mock_process_symbols
    ):
        """Test repair_wheel with debug symbol collection."""
        # Mock wheel filename parsing
        mock_match = MagicMock()
        mock_match.group.return_value = "package-1.0.0"
        mock_wheel_info.return_value = mock_match

        # Mock wheel context
        mock_ctx = MagicMock()
        mock_wheel_ctx.return_value.__enter__.return_value = mock_ctx
        mock_ctx.out_wheel = Path("output.whl")
        mock_ctx.name = Path("wheel_name")

        # Mock wheel ABI
        mock_wheel_abi = MagicMock()
        mock_wheel_abi.full_external_refs = {
            Path("ext.so"): {"manylinux_2_17_x86_64": MagicMock(libs={})}
        }

        # Mock patcher
        mock_patcher = MagicMock()

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)

            repair_wheel(
                wheel_abi=mock_wheel_abi,
                wheel_path=Path("package-1.0-py3-none-linux_x86_64.whl"),
                abis=["manylinux_2_17_x86_64"],
                lib_sdir=".libs",
                out_dir=out_dir,
                update_tags=False,
                patcher=mock_patcher,
                strip_level=StripLevel.DEBUG,
                collect_debug_symbols=True,
                debug_symbols_output=None,  # Should use default
            )

            # Should call process_symbols with debug collection enabled
            mock_process_symbols.assert_called_once()
            args, kwargs = mock_process_symbols.call_args
            libraries, strip_level, collect_debug_symbols, debug_symbols_zip = args

            assert list(libraries) == [Path("ext.so")]
            assert strip_level == StripLevel.DEBUG
            assert collect_debug_symbols is True
            assert debug_symbols_zip == out_dir / "package-1.0.0_debug_symbols.zip"

    @patch("auditwheel.repair.process_symbols")
    @patch("auditwheel.repair.InWheelCtx")
    def test_repair_wheel_with_custom_debug_output(
        self, mock_wheel_ctx, mock_process_symbols
    ):
        """Test repair_wheel with custom debug symbols output path."""
        # Mock wheel context
        mock_ctx = MagicMock()
        mock_wheel_ctx.return_value.__enter__.return_value = mock_ctx
        mock_ctx.out_wheel = Path("output.whl")
        mock_ctx.name = Path("wheel_name")

        # Mock wheel ABI
        mock_wheel_abi = MagicMock()
        mock_wheel_abi.full_external_refs = {
            Path("ext.so"): {"manylinux_2_17_x86_64": MagicMock(libs={})}
        }

        # Mock patcher
        mock_patcher = MagicMock()
        custom_debug_path = Path("/custom/debug.zip")

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)

            repair_wheel(
                wheel_abi=mock_wheel_abi,
                wheel_path=Path("package-1.0-py3-none-linux_x86_64.whl"),
                abis=["manylinux_2_17_x86_64"],
                lib_sdir=".libs",
                out_dir=out_dir,
                update_tags=False,
                patcher=mock_patcher,
                strip_level=StripLevel.DEBUG,
                collect_debug_symbols=True,
                debug_symbols_output=custom_debug_path,
            )

            # Should use custom debug symbols path
            mock_process_symbols.assert_called_once()
            args, kwargs = mock_process_symbols.call_args
            libraries, strip_level, collect_debug_symbols, debug_symbols_zip = args

            assert debug_symbols_zip == custom_debug_path

    @patch("auditwheel.repair.process_symbols")
    @patch("auditwheel.repair.InWheelCtx")
    def test_repair_wheel_backward_compatibility_strip_true(
        self, mock_wheel_ctx, mock_process_symbols
    ):
        """Test repair_wheel backward compatibility with strip=True."""
        # Mock wheel context
        mock_ctx = MagicMock()
        mock_wheel_ctx.return_value.__enter__.return_value = mock_ctx
        mock_ctx.out_wheel = Path("output.whl")
        mock_ctx.name = Path("wheel_name")

        # Mock wheel ABI
        mock_wheel_abi = MagicMock()
        mock_wheel_abi.full_external_refs = {
            Path("ext.so"): {"manylinux_2_17_x86_64": MagicMock(libs={})}
        }

        # Mock patcher
        mock_patcher = MagicMock()

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)

            repair_wheel(
                wheel_abi=mock_wheel_abi,
                wheel_path=Path("package-1.0-py3-none-linux_x86_64.whl"),
                abis=["manylinux_2_17_x86_64"],
                lib_sdir=".libs",
                out_dir=out_dir,
                update_tags=False,
                patcher=mock_patcher,
                strip=True,  # Old parameter
            )

            # Should map strip=True to StripLevel.ALL
            mock_process_symbols.assert_called_once()
            args, kwargs = mock_process_symbols.call_args
            libraries, strip_level, collect_debug_symbols, debug_symbols_zip = args

            assert strip_level == StripLevel.ALL

    def test_repair_wheel_conflicting_strip_parameters(self):
        """Test repair_wheel with conflicting strip parameters raises error."""
        mock_wheel_abi = MagicMock()
        mock_wheel_abi.full_external_refs = {}  # Pure wheel
        mock_patcher = MagicMock()

        with pytest.raises(
            ValueError, match="Cannot specify both 'strip' and 'strip_level' parameters"
        ):
            repair_wheel(
                wheel_abi=mock_wheel_abi,
                wheel_path=Path("package-1.0-py3-none-linux_x86_64.whl"),
                abis=["manylinux_2_17_x86_64"],
                lib_sdir=".libs",
                out_dir=Path("/tmp"),
                update_tags=False,
                patcher=mock_patcher,
                strip=True,
                strip_level=StripLevel.DEBUG,  # Conflicting parameters
            )

    @patch("auditwheel.repair.process_symbols")
    @patch("auditwheel.repair.InWheelCtx")
    def test_repair_wheel_no_stripping(self, mock_wheel_ctx, mock_process_symbols):
        """Test repair_wheel with no stripping (strip_level=NONE)."""
        # Mock wheel context
        mock_ctx = MagicMock()
        mock_wheel_ctx.return_value.__enter__.return_value = mock_ctx
        mock_ctx.out_wheel = Path("output.whl")
        mock_ctx.name = Path("wheel_name")

        # Mock wheel ABI
        mock_wheel_abi = MagicMock()
        mock_wheel_abi.full_external_refs = {
            Path("ext.so"): {"manylinux_2_17_x86_64": MagicMock(libs={})}
        }

        # Mock patcher
        mock_patcher = MagicMock()

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)

            repair_wheel(
                wheel_abi=mock_wheel_abi,
                wheel_path=Path("package-1.0-py3-none-linux_x86_64.whl"),
                abis=["manylinux_2_17_x86_64"],
                lib_sdir=".libs",
                out_dir=out_dir,
                update_tags=False,
                patcher=mock_patcher,
                strip_level=StripLevel.NONE,
            )

            # Should not call process_symbols when strip_level is NONE
            mock_process_symbols.assert_not_called()

    def test_repair_wheel_pure_wheel_no_processing(self):
        """Test repair_wheel returns None for pure wheels (no external refs)."""
        mock_wheel_abi = MagicMock()
        mock_wheel_abi.full_external_refs = {}  # Pure wheel
        mock_patcher = MagicMock()

        result = repair_wheel(
            wheel_abi=mock_wheel_abi,
            wheel_path=Path("package-1.0-py3-none-linux_x86_64.whl"),
            abis=["manylinux_2_17_x86_64"],
            lib_sdir=".libs",
            out_dir=Path("/tmp"),
            update_tags=False,
            patcher=mock_patcher,
            strip_level=StripLevel.DEBUG,
        )

        assert result is None

    @patch("auditwheel.repair.process_symbols")
    @patch("auditwheel.repair.InWheelCtx")
    @patch("auditwheel.repair.copylib")
    def test_repair_wheel_with_external_libraries(
        self, mock_copylib, mock_wheel_ctx, mock_process_symbols
    ):
        """Test repair_wheel processes both external libs and extensions."""
        # Mock wheel context
        mock_ctx = MagicMock()
        mock_wheel_ctx.return_value.__enter__.return_value = mock_ctx
        mock_ctx.out_wheel = Path("output.whl")
        mock_ctx.name = Path("wheel_name")

        # Mock copylib to return library paths
        mock_copylib.return_value = ("libfoo.so.1", Path("dest/libfoo.so.1"))

        # Mock wheel ABI with external libraries
        mock_libs = MagicMock()
        mock_libs.libs = {"libfoo.so.1": Path("/system/libfoo.so.1")}
        mock_wheel_abi = MagicMock()
        mock_wheel_abi.full_external_refs = {
            Path("ext.so"): {"manylinux_2_17_x86_64": mock_libs}
        }

        # Mock patcher
        mock_patcher = MagicMock()

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)

            repair_wheel(
                wheel_abi=mock_wheel_abi,
                wheel_path=Path("package-1.0-py3-none-linux_x86_64.whl"),
                abis=["manylinux_2_17_x86_64"],
                lib_sdir=".libs",
                out_dir=out_dir,
                update_tags=False,
                patcher=mock_patcher,
                strip_level=StripLevel.DEBUG,
            )

            # Should process both external libraries and extensions
            mock_process_symbols.assert_called_once()
            args, kwargs = mock_process_symbols.call_args
            libraries, strip_level, collect_debug_symbols, debug_symbols_zip = args

            # Should include both the copied library and the extension
            library_paths = list(libraries)
            assert Path("dest/libfoo.so.1") in library_paths
            assert Path("ext.so") in library_paths
            assert len(library_paths) == 2
