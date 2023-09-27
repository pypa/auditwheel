from __future__ import annotations

import os
from os.path import basename, realpath, relpath
from typing import Iterator

from elftools.common.exceptions import ELFError
from elftools.elf.elffile import ELFFile
from sqlelf import elf, sql

from .lddtree import parse_ld_paths


def elf_read_dt_needed(fn: str) -> list[str]:
    sql_engine = sql.make_sql_engine([fn], recursive=False,
                                     cache_flags=elf.CacheFlag.DYNAMIC_ENTRIES | elf.CacheFlag.STRINGS)
    results = sql_engine.execute("""
                        SELECT elf_strings.value
                        FROM elf_dynamic_entries
                        INNER JOIN elf_strings
                              ON elf_dynamic_entries.value = elf_strings.offset
                        WHERE elf_dynamic_entries.tag = 'NEEDED'
                       """
    )
    return list(results)


def elf_file_filter(paths: Iterator[str]) -> Iterator[tuple[str, ELFFile]]:
    """Filter through an iterator of filenames and load up only ELF
    files
    """

    for path in paths:
        if path.endswith(".py"):
            continue
        else:
            try:
                with open(path, "rb") as f:
                    candidate = ELFFile(f)
                    yield path, candidate
            except ELFError:
                # not an elf file
                continue


def elf_find_ucs2_symbols(elf: ELFFile) -> Iterator[str]:
    section = elf.get_section_by_name(".dynsym")
    if section is not None:
        # look for UCS2 symbols that are externally referenced
        for sym in section.iter_symbols():
            if (
                "PyUnicodeUCS2_" in sym.name
                and sym["st_shndx"] == "SHN_UNDEF"
                and sym["st_info"]["type"] == "STT_FUNC"
            ):
                yield sym.name


def elf_references_PyFPE_jbuf(elf: ELFFile) -> bool:
    offending_symbol_names = ("PyFPE_jbuf", "PyFPE_dummy", "PyFPE_counter")
    section = elf.get_section_by_name(".dynsym")
    if section is not None:
        # look for symbols that are externally referenced
        for sym in section.iter_symbols():
            if (
                sym.name in offending_symbol_names
                and sym["st_shndx"] == "SHN_UNDEF"
                and sym["st_info"]["type"] in ("STT_FUNC", "STT_NOTYPE")
            ):
                return True
    return False


def elf_is_python_extension(
    fn: str, sql_engine: sql.SQLEngine
) -> tuple[bool, int | None]:
    modname = basename(fn).split(".", 1)[0]
    # TODO(fzakaria): A bit annoying but SQLite doesn't support
    # bindings of list. We can perhaps rethink this or fetch all
    # symbols and then filter in Python.
    sql = f"""
        SELECT
            CASE name
                WHEN 'init{modname}' THEN 2
                WHEN 'PyInit_{modname}' THEN 3
                WHEN '_cffi_pypyinit_{modname}' THEN 2
                ELSE -1
            END AS python_version
        FROM elf_symbols
        WHERE name IN ('init{modname}', 'PyInit_{modname}', '_cffi_pypyinit_{modname}')
              AND exported = TRUE
              AND type = 'FUNC'
        LIMIT 1
            """
    results = list(sql_engine.execute(sql))

    if len(results) == 0:
        return False, None

    python_version = results[0]["python_version"]
    assert python_version in (2, 3), "Invalid python version"

    return True, python_version


def elf_read_rpaths(fn: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"rpaths": [], "runpaths": []}

    with open(fn, "rb") as f:
        elf = ELFFile(f)
        section = elf.get_section_by_name(".dynamic")
        if section is None:
            return result

        for t in section.iter_tags():
            if t.entry.d_tag == "DT_RPATH":
                result["rpaths"] = parse_ld_paths(t.rpath, root="/", path=fn)
            elif t.entry.d_tag == "DT_RUNPATH":
                result["runpaths"] = parse_ld_paths(t.runpath, root="/", path=fn)

    return result


def is_subdir(path: str, directory: str) -> bool:
    if path is None:
        return False

    path = realpath(path)
    directory = realpath(directory)

    relative = relpath(path, directory)
    if relative.startswith(os.pardir):
        return False
    return True


def get_undefined_symbols(path: str) -> set[str]:
    undef_symbols = set()
    with open(path, "rb") as f:
        elf = ELFFile(f)
        section = elf.get_section_by_name(".dynsym")
        if section is not None:
            # look for all undef symbols
            for sym in section.iter_symbols():
                if sym["st_shndx"] == "SHN_UNDEF":
                    undef_symbols.add(sym.name)
    return undef_symbols


def filter_undefined_symbols(
    path: str, symbols: dict[str, list[str]]
) -> dict[str, list[str]]:
    if not symbols:
        return {}
    undef_symbols = set("*") | get_undefined_symbols(path)
    result = {}
    for lib, sym_list in symbols.items():
        intersection = set(sym_list) & undef_symbols
        if intersection:
            result[lib] = sorted(intersection)
    return result
