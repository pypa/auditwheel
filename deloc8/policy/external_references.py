import re
from typing import Tuple, Dict, List

from elftools.elf.elffile import ELFFile

from ..linkertools import (ld_library_paths, locate_with_ldpaths,
                           locate_with_ld_so)
from ..readelf import elf_inspect_dynamic


def lib_whitelist_policy(lib: str) -> Tuple[bool, float]:
    from . import POLICY_PRIORITY_HIGHEST, _POLICY
    if re.match('^libpython\d\.\dm?.so(.\d)*$', lib):
        # libpython is always allowed
        return True, POLICY_PRIORITY_HIGHEST

    priority = max(
        [p['priority'] for p in _POLICY if lib in p['lib_whitelist']],
        default=None)
    if priority is None:
        return False, 0
    return True, priority


def lib_exteral_referenence_policy(soname: str, rpaths: List[str]) -> Dict:
    from . import POLICY_PRIORITY_HIGHEST, POLICY_PRIORITY_LOWEST

    is_whitelisted, priority = lib_whitelist_policy(soname)
    if is_whitelisted:
        return {'policy_priority': priority, 'note': 'whitelist'}

    resolved = locate_with_ldpaths(soname, rpaths)
    if resolved is not None:
        return {
            'policy_priority': POLICY_PRIORITY_HIGHEST,
            'note': 'RPATH',
            'path': resolved
        }

    resolved = locate_with_ldpaths(soname, ld_library_paths())
    if resolved is not None:
        return {
            'policy_priority': POLICY_PRIORITY_LOWEST,
            'path': resolved,
            'note': 'LD_LIBRARY_PATH'
        }

    resolved = locate_with_ld_so(soname)
    if resolved is not None:
        return {
            'policy_priority': POLICY_PRIORITY_LOWEST,
            'path': resolved,
            'note': 'LD_CONF'
        }

    return {
        'policy_priority': POLICY_PRIORITY_LOWEST,
        'path': None,
        'note': 'NOT FOUND'
    }


def elf_exteral_referenence_policy(fn: str, elf: ELFFile):
    sonames, rpaths = elf_inspect_dynamic(fn, elf)
    return {lib: lib_exteral_referenence_policy(lib, rpaths)
            for lib in sonames}
