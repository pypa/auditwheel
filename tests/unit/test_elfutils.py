from unittest.mock import patch, Mock, MagicMock

import pytest
from elftools.common.exceptions import ELFError

from auditwheel.elfutils import elf_read_dt_needed, elf_file_filter, \
    elf_find_versioned_symbols, elf_find_ucs2_symbols, elf_references_PyFPE_jbuf


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

    def test_missing_section(self, elffile_mock, open_mock):
        # GIVEN
        open_mock.return_value.__enter__.return_value = Mock()
        elffile_mock.return_value.get_section_by_name.return_value = None

        # THEN
        with pytest.raises(ValueError):
            # WHEN
            elf_read_dt_needed("/fake.so")

    def test_needed_libs(self, elffile_mock, open_mock):
        # GIVEN
        open_mock.return_value.__enter__.return_value = Mock()
        section_mock = Mock()
        tag1 = Mock(needed="libz.so")
        tag1.entry.d_tag = "DT_NEEDED"
        tag2 = Mock(needed="libfoo.so")
        tag2.entry.d_tag = "DT_NEEDED"
        section_mock.iter_tags.return_value = [tag1, tag2]
        elffile_mock.return_value.get_section_by_name.return_value = section_mock

        # WHEN
        needed = elf_read_dt_needed("/fake.so")

        # THEN
        assert len(needed) == 2
        assert "libz.so" in needed
        assert "libfoo.so" in needed


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


class TestElfFindVersionedSymbols:

    def test_find_symbols(self):
        # GIVEN
        elf = Mock()
        verneed = Mock()
        verneed.configure_mock(name="foo-lib")
        veraux = Mock()
        veraux.configure_mock(name="foo-lib")
        elf.get_section_by_name.return_value.iter_versions.return_value = (
            (verneed, [veraux]),
        )

        # WHEN
        symbols = list(elf_find_versioned_symbols(elf))

        # THEN
        assert symbols == [("foo-lib", "foo-lib")]

    @pytest.mark.parametrize('ld_name', ['ld-linux', 'ld64.so.2', 'ld64.so.1'])
    def test_only_ld_linux(self, ld_name):
        # GIVEN
        elf = Mock()
        verneed = Mock()
        verneed.configure_mock(name=ld_name)
        veraux = Mock()
        veraux.configure_mock(name="foo-lib")
        elf.get_section_by_name.return_value.iter_versions.return_value = (
            (verneed, [veraux]),
        )

        # WHEN
        symbols = list(elf_find_versioned_symbols(elf))

        # THEN
        assert len(symbols) == 0

    def test_empty_section(self):
        # GIVEN
        elf = Mock()
        elf.get_section_by_name.return_value = None

        # WHEN
        symbols = list(elf_find_versioned_symbols(elf))

        # THEN
        assert len(symbols) == 0


class TestFindUcs2Symbols:

    def test_elf_find_ucs2_symbols(self):
        # GIVEN
        elf = Mock()

        asunicode = MockSymbol("PyUnicodeUCS2_AsUnicode",
                               st_shndx="SHN_UNDEF",
                               st_info=dict(type="STT_FUNC"))
        symbols = (asunicode, Mock())
        symbols[1].name = "foobar"
        elf.get_section_by_name.return_value.iter_symbols.return_value = symbols

        # WHEN
        symbols = list(elf_find_ucs2_symbols(elf))

        # THEN
        assert len(symbols) == 1
        assert symbols[0] == 'PyUnicodeUCS2_AsUnicode'

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
        symbols = (MockSymbol("PyFPE_jbuf",
                              st_shndx="SHN_UNDEF",
                              st_info=dict(type="STT_FUNC")),)

        elf.get_section_by_name.return_value.iter_symbols.return_value = symbols

        # WHEN/THEN
        assert elf_references_PyFPE_jbuf(elf) is True

    def test_elf_references_pyfpe_jbuf_false(self):
        # GIVEN
        elf = Mock()
        symbols = (MockSymbol("SomeSymbol",
                              st_shndx="SHN_UNDEF",
                              st_info=dict(type="STT_FUNC")),)

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

