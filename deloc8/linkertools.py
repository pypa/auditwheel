import re
import os
import functools
import logging
from subprocess import check_output
from typing import List, Optional, TypeVar, Dict
log = logging.getLogger(__name__)

SONAME_WHITELIST = [
    'libpanelw.so.5',
    'libncursesw.so.5',
    'libgcc_s.so.1',
    'libstdc++.so.6',
    'libm.so.6',
    'libdl.so.2',
    'librt.so.1',
    'libcrypt.so.1',
    'libc.so.6',
    'libnsl.so.1',
    'libutil.so.1',
    'libpthread.so.0',
    'libX11.so.6',
    'libXext.so.6',
    'libXrender.so.1',
    'libICE.so.6',
    'libSM.so.6',
    'libGL.so.1',
    'libgobject-2.0.so.0',
    'libgthread-2.0.so.0',
    'libglib-2.0.so.0',
    'ld-linux-x86-64.so.2',
    'ld.so',
]


def locate_with_ldpaths(lib: str, ldpaths: List[str]=[]) -> Optional[str]:
    log.debug('locate_with_ldpaths: %s %s', lib, ldpaths)
    for ldpath in ldpaths:
        path = os.path.join(ldpath, lib)
        if os.path.exists(path):
            return path
    return None


def parse_ld_path(ldpath: str) -> List[str]:
    """Parse colon-deliminted ldpath like LD_LIBRARY_PATH"""
    parsed = []
    for path in ldpath.split(':'):
        parsed.append(path.replace('//', '/'))
    return parsed


@functools.lru_cache()
def ld_library_paths() -> List[str]:
    """Load the LD_LIBRARY_PATH env variable"""
    return parse_ld_path(os.environ.get('LD_LIBRARY_PATH'))


@functools.lru_cache()
def load_ld_so_conf() -> Dict[str, str]:
    sonames = {}
    for line in check_output(['/sbin/ldconfig', '-p']).decode(
            'utf-8').splitlines():
        m = re.match(r'\t(.*) (\(.*\)) => (.*)', line)
        if m:
            # TODO(rmcgibbo) we're dropping info about the multiarch,
            # x64 info, etc
            sonames[(m.group(1))] = m.group(3)
    return sonames


def locate_with_ld_so(lib: str) -> Optional[str]:
    """Resolve a soname using the system paths from /etc/ld.so.conf"""
    ldconf = load_ld_so_conf()
    return ldconf.get(lib, None)


def is_whitelisted(lib: str) -> bool:
    if lib in SONAME_WHITELIST:
        return True
    if re.match('^libpython\d\.\dm?.so(.\d)*$', lib):
        return True
    return False
