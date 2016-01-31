from os.path import basename
from auditwheel.policy.external_references import LIBPYTHON_RE

from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError  # type: ignore
from typing import Iterator, Tuple, Optional



def elf_file_filter(paths: Iterator[str]) -> Iterator[Tuple[str, ELFFile]]:
    """Filter through an iterator of filenames and load up only ELF
    files
    """

    for path in paths:
        if path.endswith('.py'):
            continue
        else:
            try:
                with open(path, 'rb') as f:
                    candidate = ELFFile(f)
                    yield path, candidate
            except ELFError:
                # not an elf file
                continue


def elf_find_versioned_symbols(elf: ELFFile) -> Iterator[Tuple[str, str]]:
    section = elf.get_section_by_name(b'.gnu.version_r')
    if section is None:
        return []

    for verneed, verneed_iter in section.iter_versions():
        if verneed.name.decode('utf-8').startswith('ld-linux'):
            continue
        for vernaux in verneed_iter:
            yield (verneed.name.decode('utf-8'), vernaux.name.decode('utf-8'))


def elf_find_ucs2_symbols(elf: ELFFile) -> Iterator[str]:
    section = elf.get_section_by_name(b'.dynsym')
    if section is None:
        return []

    # look for UCS2 symbols that are externally referenced
    for sym in section.iter_symbols():
        if (b'PyUnicodeUCS2_' in sym.name and
            sym['st_shndx'] == 'SHN_UNDEF' and
            sym['st_info']['type'] == 'STT_FUNC'):

            yield sym.name


def elf_is_python_extension(fn, elf) -> Tuple[bool, Optional[int]]:
    modname = basename(fn).split('.', 1)[0]
    module_init_f = {'init' + modname: 2, 'PyInit_' + modname: 3}

    sect = elf.get_section_by_name(b'.dynsym')
    if sect is None:
        return False, None

    for sym in sect.iter_symbols():
        if (sym.name.decode('utf-8') in module_init_f and
                sym['st_shndx'] != 'SHN_UNDEF' and
                sym['st_info']['type'] == 'STT_FUNC'):

            return True, module_init_f[sym.name.decode('utf-8')]

    return False, None
