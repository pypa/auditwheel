import re
from itertools import repeat
from os.path import basename
from typing import Iterator, Tuple

from .genericpkgctx import InGenericPkgCtx
from .lddtree import elf_file_filter, elf_match_dt_needed
from .policy.external_references import LIBPYTHON_RE

LIBPYTHONS_RE = {
    2: re.compile('^libpython2\.\dm?.so(.\d)*$'),
    3: re.compile('^libpython3\.\dm?.so(.\d)*$')
}


def iter_wheel_exposed_symbols(wheel_file: str) -> Iterator[Tuple[str, str, str, str]]:
    """Get all of the exposed symbols in the dynamic shared object
    files in a wheel.
    """
    with InGenericPkgCtx(wheel_file) as ctx:
        for fn, elf in elf_file_filter(ctx.iter_files()):
            links_python = False
            prepend_fn = lambda: (basename(fn), ) + t,
            
            for py_major_ver, py_re in LIBPYTHONS_RE.items():
                if elf_match_dt_needed(elf, py_re):
                    links_python = True

                    yield from map(
                        lambda t: (basename(fn), ) + t, filter_init_symbol(
                            iter_elf_exposed_symbols(elf), py_major_ver, fn))

            if not links_python:
                yield from map(lambda t: (basename(fn), ) + t,
                               iter_elf_exposed_symbols(elf))


def iter_elf_exposed_symbols(elf) -> Iterator[Tuple[str, str, str]]:
    """Get all the "exposed" symbols in an ELF.

    By "exposed", we mean symbols that
    1. Have STB_GLOBAL, described as:
        Global symbols are visible to all object files being combined.
        One file's definition of a global symbol will satisfy another
        file's undefined reference to the same global symbol.
        (http://www.sco.com/developers/gabi/latest/ch4.symtab.html)
    2. Are defined in this ELF file.
    3. Are functions (we could check for other stuff like data,
       but I'm seeing some false positives there)
    """

    def is_exposed(s):
        return (s.name not in (b'_init', b'_fini') and
                s['st_info']['type'] == 'STT_FUNC' and
                s['st_shndx'] != 'SHN_UNDEF' and (
                    s['st_other']['visibility'] == 'STV_DEFAULT' or
                    s['st_info']['bind'] == 'STB_GLOBAL'))

    sect = elf.get_section_by_name(b'.dynsym')
    if sect is not None:
        for s in filter(is_exposed, sect.iter_symbols()):
            yield (s.name.decode('utf-8'), s['st_other']['visibility'],
                   s['st_info']['bind'])


def filter_init_symbol(symbols: Iterator[Tuple[str,str,str]], py_major_ver: int, fn:
                       str) -> Iterator[Tuple[str,str,str]]:
    """Filter out the module initialization function's name
    (init<modname> or PyInit_<modname> required by the CPython C API
    """
    modname = basename(fn).split('.', 1)[0]
    module_init_f = {2: 'init', 3: 'PyInit_'}[py_major_ver] + modname

    for s in symbols:
        if s[0] != module_init_f:
            yield s
