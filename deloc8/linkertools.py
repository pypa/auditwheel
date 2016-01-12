import re
import os
import functools
import logging
from subprocess import check_output
from typing import List, Optional, TypeVar, Dict
log = logging.getLogger(__name__)


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
