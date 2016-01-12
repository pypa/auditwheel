import re
import os
import json
import logging
from functools import reduce
from typing import Tuple, Dict, List, Set, Any

from elftools.elf.elffile import ELFFile

from . import POLICY_PRIORITY_HIGHEST, load_policies
from ..lddtree import parse_elf

log = logging.getLogger(__name__)


def elf_exteral_referenences(fn: str, wheel_path: str):
    policies = load_policies()
    tree = parse_elf(fn)

    def filter_libs(libs, whitelist):
        for lib in libs:
            if 'ld-linux' in lib:
                # always exclude ld-linux.so
                continue
            if re.match('^libpython\d\.\dm?.so(.\d)*$', lib):
                # always exclude libpythonXY
                continue
            if lib in whitelist:
                # exclude any libs in the whitelist
                continue
            yield lib

    def get_req_external(libs: Set[str], whitelist: Set[str]):
        # recurisvely get all the required external libraries
        return reduce(set.union, (get_req_external(
            set(filter_libs(tree['libs'][lib]['needed'], whitelist)),
            whitelist) for lib in libs), libs)

    ret = {}  # type: Dict[str, Dict[str, Any]]
    for p in policies:
        needed_external_libs = []  # type: List[str]

        if not (p['name'] == 'linux' and p['priority'] == 0):
            # special-case the generic linux platform here, because it
            # doesn't have a whitelist. or, you could say its
            # whitelist is the complete set of all libraries. so nothing
            # is considered "external" that needs to be copied in.
            whitelist = set(p['lib_whitelist'])
            needed_external_libs = get_req_external(
                set(filter_libs(tree['needed'], whitelist)), whitelist)  # type: List[str]

        pol_ext_deps = {}
        for lib in needed_external_libs:
            if is_subdir(tree['libs'][lib]['realpath'], wheel_path):
                # we didn't filter libs that resolved via RPATH out
                # earlier because we wanted to make sure to pick up
                # our elf's indirect dependencies. But now we want to
                # filter these ones out, since they're not "external".
                log.debug('RPATH FTW: %s', lib)
                continue
            pol_ext_deps[lib] = tree['libs'][lib]['path']
        ret[p['name']] = {'external libs': pol_ext_deps,
                          'priority': p['priority']}
    return ret


def is_subdir(path, directory):
    if path is None:
        return False

    path = os.path.realpath(path)
    directory = os.path.realpath(directory)
    relative = os.path.relpath(path, directory)
    if relative.startswith(os.pardir):
        return False
    return True
