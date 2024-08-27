from __future__ import annotations

from os.path import basename
from pathlib import Path
from typing import Iterator

from elftools.common.exceptions import ELFError
from elftools.elf.dynamic import DynamicSegment
from elftools.elf.elffile import ELFFile

from .lddtree import parse_ld_paths
from .libc import Libc


def elf_read_dt_needed(fn: str) -> list[str]:
    needed = []
    with open(fn, "rb") as f:
        elf = ELFFile(f)
        section = elf.get_section_by_name(".dynamic")
        if section is None:
            raise ValueError("Could not find soname in %s" % fn)

        for t in section.iter_tags():
            if t.entry.d_tag == "DT_NEEDED":
                needed.append(t.needed)

    return needed


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


def elf_find_versioned_symbols(elf: ELFFile) -> Iterator[tuple[str, str]]:
    section = elf.get_section_by_name(".gnu.version_r")

    if section is not None:
        for verneed, verneed_iter in section.iter_versions():
            if verneed.name.startswith("ld-linux") or verneed.name in [
                "ld64.so.2",
                "ld64.so.1",
            ]:
                continue
            for vernaux in verneed_iter:
                yield (verneed.name, vernaux.name)


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


def elf_is_python_extension(fn: str, elf: ELFFile) -> tuple[bool, int | None]:
    modname = basename(fn).split(".", 1)[0]
    module_init_f = {
        "init" + modname: 2,
        "PyInit_" + modname: 3,
        "_cffi_pypyinit_" + modname: 2,
    }

    sect = elf.get_section_by_name(".dynsym")
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


def is_subdir(path: str | Path | None, directory: str | Path) -> bool:
    if path is None:
        return False

    path = Path(path).resolve()
    directory = Path(directory).resolve()

    return directory in path.parents


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


def elf_get_platform_info(path: str) -> tuple[Libc | None, str | None]:
    with open(path, "rb") as f:
        try:
            elf = ELFFile(f)
        except ELFError:
            return (None, None)
        arch = {
            "x64": "x86_64",
            "x86": "i686",
            "AArch64": "aarch64",
            "64-bit PowerPC": "ppc64",
            "IBM S/390": "s390x",
            "ARM": "armv7l",
            "RISC-V": "riscv64",
        }[elf.get_machine_arch()]
        if arch == "ppc64" and elf.header.e_ident.EI_DATA == "ELFDATA2LSB":
            arch = "ppc64le"

        libc = None
        for seg in elf.iter_segments():
            if not isinstance(seg, DynamicSegment):
                continue
            for tag in seg.iter_tags():
                if tag.entry.d_tag == "DT_NEEDED":
                    if tag.needed == "libc.so.6":
                        libc = Libc.GLIBC
                        break
                    if tag.needed.startswith("libc.musl-"):
                        libc = Libc.MUSL
                        break
            break
        return (libc, arch)
