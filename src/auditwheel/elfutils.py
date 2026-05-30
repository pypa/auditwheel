from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from elftools.common.exceptions import ELFError
from elftools.elf.dynamic import DynamicSection
from elftools.elf.elffile import ELFFile
from elftools.elf.gnuversions import GNUVerNeedSection
from elftools.elf.sections import Section, SymbolTableSection

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

    _SectionT = TypeVar("_SectionT", bound=Section)


def _get_section_by_type(elf: ELFFile, type_: type[_SectionT]) -> _SectionT | None:
    name = {
        DynamicSection: ".dynamic",
        GNUVerNeedSection: ".gnu.version_r",
        SymbolTableSection: ".dynsym",
    }[type_]
    section = elf.get_section_by_name(name)
    if TYPE_CHECKING:
        assert section is None or isinstance(section, type_)
    return section


def elf_read_dt_needed(fn: Path) -> list[str]:
    needed: list[str] = []
    with fn.open("rb") as f:
        elf = ELFFile(f)
        section = _get_section_by_type(elf, DynamicSection)
        if section is None:
            msg = f"Could not find soname in {fn}"
            raise ValueError(msg)
        needed.extend(t.needed for t in section.iter_tags() if t.entry.d_tag == "DT_NEEDED")  # type: ignore[attr-defined]
    return needed


def elf_file_filter(paths: Iterable[Path]) -> Iterator[tuple[Path, ELFFile]]:
    """Filter through an iterator of filenames and load up only ELF
    files
    """
    for path in paths:
        if path.name.endswith(".py"):
            continue
        else:
            try:
                with path.open("rb") as f:
                    candidate = ELFFile(f)
                    yield path, candidate
            except ELFError:
                # not an elf file
                continue


def elf_find_versioned_symbols(elf: ELFFile) -> Iterator[tuple[str, str]]:
    if section := _get_section_by_type(elf, GNUVerNeedSection):
        for verneed, verneed_iter in section.iter_versions():
            if TYPE_CHECKING:
                # this should be enforced some other way in pyelftools
                assert verneed.name is not None
            if verneed.name.startswith("ld-linux") or verneed.name in [
                "ld64.so.2",
                "ld64.so.1",
            ]:
                continue
            for vernaux in verneed_iter:
                yield (verneed.name, vernaux.name)


def elf_find_ucs2_symbols(elf: ELFFile) -> Iterator[str]:
    if section := _get_section_by_type(elf, SymbolTableSection):
        # look for UCS2 symbols that are externally referenced
        for sym in section.iter_symbols():
            if (
                "PyUnicodeUCS2_" in sym.name
                and sym["st_shndx"] == "SHN_UNDEF"
                and sym["st_info"]["type"] == "STT_FUNC"
            ):
                yield sym.name


def elf_references_pyfpe_jbuf(elf: ELFFile) -> bool:
    offending_symbol_names = ("PyFPE_jbuf", "PyFPE_dummy", "PyFPE_counter")
    if section := _get_section_by_type(elf, SymbolTableSection):
        # look for symbols that are externally referenced
        for sym in section.iter_symbols():
            if (
                sym.name in offending_symbol_names
                and sym["st_shndx"] == "SHN_UNDEF"
                and sym["st_info"]["type"] in ("STT_FUNC", "STT_NOTYPE")
            ):
                return True
    return False


def elf_is_python_extension(fn: Path, elf: ELFFile) -> tuple[bool, int | None]:
    modname = fn.name.split(".", 1)[0]
    module_init_f = {
        "init" + modname: 2,
        "PyInit_" + modname: 3,
        "_cffi_pypyinit_" + modname: 2,
    }

    sect = _get_section_by_type(elf, SymbolTableSection)
    if sect is None:
        return False, None

    for sym in sect.iter_symbols():
        if (
            sym.name in module_init_f
            and sym["st_shndx"] != "SHN_UNDEF"
            and sym["st_info"]["type"] == "STT_FUNC"
        ):
            return True, module_init_f[sym.name]

    return False, None


def get_undefined_symbols(path: Path) -> set[str]:
    undef_symbols = set()
    with path.open("rb") as f:
        elf = ELFFile(f)
        if section := _get_section_by_type(elf, SymbolTableSection):
            # look for all undef symbols
            # if the symbol is weak don't consider it as undefined, it's "optional"
            for sym in section.iter_symbols():
                if sym["st_shndx"] == "SHN_UNDEF" and sym["st_info"]["bind"] != "STB_WEAK":
                    undef_symbols.add(sym.name)
    return undef_symbols


def filter_undefined_symbols(
    path: Path,
    symbols: dict[str, frozenset[str]],
) -> dict[str, list[str]]:
    if not symbols:
        return {}
    undef_symbols = set("*") | get_undefined_symbols(path)
    result = {}
    for lib, sym_list in symbols.items():
        intersection = sym_list & undef_symbols
        if intersection:
            result[lib] = sorted(intersection)
    return result
