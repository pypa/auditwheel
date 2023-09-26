from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from elftools.common.exceptions import ELFError

from auditwheel.elfutils import (
    elf_file_filter,
    elf_find_ucs2_symbols,
    elf_read_dt_needed,
    elf_references_PyFPE_jbuf,
)


class MockSymbol(dict):
    """Mock representing a Symbol in ELFTools."""

    def __init__(self, name, **kwargs):
        super().__init__(**kwargs)
        self._name = name

    @property
    def name(self):
        return self._name


@patch("auditwheel.elfutils.open")
@patch("auditwheel.elfutils.ELFFile")
class TestElfReadDt:

    def test_needed_libs(self, elffile_mock, open_mock):
        # WHEN
        needed = elf_read_dt_needed("/bin/ls")

        # THEN
        assert len(needed) > 0


@patch("auditwheel.elfutils.open")
@patch("auditwheel.elfutils.ELFFile")
class TestElfFileFilter:
    def test_filter(self, elffile_mock, open_mock):
        result = elf_file_filter(["file1.so", "file2.so"])
        assert len(list(result)) == 2

    def test_some_py_files(self, elffile_mock, open_mock):
        result = elf_file_filter(["file1.py", "file2.so", "file3.py"])
        assert len(list(result)) == 1

    def test_not_elf(self, elffile_mock, open_mock):
        # GIVEN
        elffile_mock.side_effect = ELFError

        # WHEN
        result = elf_file_filter(["file1.notelf", "file2.notelf"])

        # THEN
        assert len(list(result)) == 0


class TestFindUcs2Symbols:
    def test_elf_find_ucs2_symbols(self):
        # GIVEN
        elf = Mock()

        asunicode = MockSymbol(
            "PyUnicodeUCS2_AsUnicode",
            st_shndx="SHN_UNDEF",
            st_info=dict(type="STT_FUNC"),
        )
        symbols = (asunicode, Mock())
        symbols[1].name = "foobar"
        elf.get_section_by_name.return_value.iter_symbols.return_value = symbols

        # WHEN
        symbols = list(elf_find_ucs2_symbols(elf))

        # THEN
        assert len(symbols) == 1
        assert symbols[0] == "PyUnicodeUCS2_AsUnicode"

    def test_elf_find_ucs2_symbols_no_symbol(self):
        # GIVEN
        elf = Mock()

        symbols = (MockSymbol("FooSymbol"),)
        elf.get_section_by_name.return_value.iter_symbols.return_value = symbols

        # WHEN/THEN
        symbols = list(elf_find_ucs2_symbols(elf))
        assert len(symbols) == 0


class TestElfReferencesPyPFE:
    def test_elf_references_pyfpe_jbuf(self):
        # GIVEN
        elf = Mock()
        symbols = (
            MockSymbol(
                "PyFPE_jbuf", st_shndx="SHN_UNDEF", st_info=dict(type="STT_FUNC")
            ),
        )

        elf.get_section_by_name.return_value.iter_symbols.return_value = symbols

        # WHEN/THEN
        assert elf_references_PyFPE_jbuf(elf) is True

    def test_elf_references_pyfpe_jbuf_false(self):
        # GIVEN
        elf = Mock()
        symbols = (
            MockSymbol(
                "SomeSymbol", st_shndx="SHN_UNDEF", st_info=dict(type="STT_FUNC")
            ),
        )

        elf.get_section_by_name.return_value.iter_symbols.return_value = symbols

        # WHEN/THEN
        assert elf_references_PyFPE_jbuf(elf) is False

    def test_elf_references_pyfpe_jbuf_no_section(self):
        # GIVEN
        elf = Mock()

        # WHEN
        elf.get_section_by_name.return_value = None

        # WHEN/THEN
        assert elf_references_PyFPE_jbuf(elf) is False
