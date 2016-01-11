SONAME_WHITELIST = [
    'libpanelw.so.5', 'libncursesw.so.5', 'libgcc_s.so.1',
    'libstdc++.so.6', 'libm.so.6', 'libdl.so.2', 'librt.so.1',
    'libcrypt.so.1', 'libc.so.6', 'libnsl.so.1', 'libutil.so.1',
    'libpthread.so.0', 'libX11.so.6', 'libXext.so.6',
    'libXrender.so.1', 'libICE.so.6', 'libSM.so.6', 'libGL.so.1',
    'libgobject-2.0.so.0', 'libgthread-2.0.so.0', 'libglib-2.0.so.0',
    'ld-linux-x86-64.so.2', 'ld.so',
]


import os
import re
import logging
import functools
from subprocess import check_output
from typing import List

from elftools.elf.dynamic import DynamicSection
from elftools.elf.elffile import ELFFile

log = logging.getLogger(__name__)


def elf_inspect_dynamic(elf):
    section = elf.get_section_by_name(b'.dynamic')
    data = {'DT_NEEDED': [],
            'DT_RPATH': []}

    if section is not None:
        for tag in section.iter_tags():
            if tag.entry.d_tag == 'DT_NEEDED':
                data['DT_NEEDED'].append(tag.needed.decode('utf-8'))
            elif tag.entry.d_tag == 'DT_RPATH':
                data['DT_RPATH'].append(tag.rpath.decode('utf-8'))
                
    return data['DT_NEEDED'], data['DT_RPATH']


def locate_with_ldpaths(lib, ldpaths=[]):
    # log.debug('locate_with_ldpaths: %s %s', lib, ldpaths)
    for ldpath in ldpaths:
        path = os.path.join(ldpath, lib)
        if os.path.exists(path):
            return path
    return None


def load_ld_library_path():
    ldpaths = []
    env_ldpaths = parse_ld_path(os.environ.get('LD_LIBRARY_PATH'))
    return env_ldpaths


def parse_ld_path(ldpath : str) -> List[str]:
    """Parse colon-deliminted ldpath like LD_LIBRARY_PATH"""
    parsed = []
    for path in ldpath.split(':'):
        parsed.append(os.path.normpath(path).replace('//', '/'))
    return parsed


def locate_with_ld_so(lib):
    ldconf = load_ld_so_conf()
    return ldconf.get(lib, None)
    

@functools.lru_cache()
def load_ld_so_conf():
    sonames = {}
    for line in check_output(['/sbin/ldconfig', '-p']).decode('utf-8').splitlines():
        m = re.match(r'\t(.*) (\(.*\)) => (.*)', line)
        if m:
            # TODO(rmcgibbo) we're dropping info about the multiarch,
            # x64 info, etc
            sonames[(m.group(1))] = m.group(3)
    return sonames

def is_whitelisted(soname):
    if soname in SONAME_WHITELIST:
        return True
    if re.match('^libpython\d\.\dm?.so(.\d)*$', soname):
        return True
    return False
    
                
                
        
