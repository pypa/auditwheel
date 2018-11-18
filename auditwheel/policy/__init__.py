import sys
import json
import platform as _platform_module
from typing import Optional
from os.path import join, dirname, abspath
import logging

logger = logging.getLogger(__name__)

_sys_map = {'linux2': 'linux',
            'linux': 'linux',
            'darwin': 'osx',
            'win32': 'win',
            'openbsd5': 'openbsd'}
non_x86_linux_machines = {'armv6l', 'armv7l', 'ppc64le'}
platform = _sys_map.get(sys.platform, 'unknown')
linkage = _platform_module.architecture()[1]

# https://docs.python.org/3/library/platform.html#platform.architecture
bits = 8 * (8 if sys.maxsize > 2 ** 32 else 4)

_PLATFORM_REPLACEMENT_MAP = {
    'manylinux1_x86_64': ['linux_x86_64'],
    'manylinux2010_x86_64': ['linux_x86_64'],
    'manylinux1_i686': ['linux_i686'],
    'manylinux2010_i686': ['linux_i686'],
}

# XXX: this could be weakened. The show command _could_ run on OS X or
# Windows probably, but there's not much reason to inspect foreign package
# that won't run on the platform.
if platform != 'linux':
    logger.critical('Error: This tool only supports Linux')
    sys.exit(1)

def get_arch_name():
    if _platform_module.machine() in non_x86_linux_machines:
        return _platform_module.machine()
    else:
        return {64: 'x86_64', 32: 'i686'}[bits]

_ARCH_NAME = get_arch_name()


with open(join(dirname(abspath(__file__)), 'policy.json')) as f:
    _POLICIES = json.load(f)
    for p in _POLICIES:
        p['name'] = p['name'] + '_' + _ARCH_NAME

POLICY_PRIORITY_HIGHEST = max(p['priority'] for p in _POLICIES)
POLICY_PRIORITY_LOWEST = min(p['priority'] for p in _POLICIES)


def load_policies():
    return _POLICIES


def _load_policy_schema():
    with open(join(dirname(abspath(__file__)), 'policy-schema.json')) as f:
        schema = json.load(f)
    return schema


def get_policy_name(priority: int) -> Optional[str]:
    matches = [p['name'] for p in _POLICIES if p['priority'] == priority]
    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise RuntimeError('Internal error. priorities should be unique')
    return matches[0]


def get_priority_by_name(name: str):
    matches = [p['priority'] for p in _POLICIES if p['name'] == name]
    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise RuntimeError('Internal error. Policies should be unique.')
    return matches[0]


def get_replace_platforms(name: str):
    """Extract platform tag replacement rules from policy

    >>> get_replace_platforms('linux_x86_64')
    []
    >>> get_replace_platforms('linux_i686')
    []
    >>> get_replace_platforms('manylinux1_x86_64')
    ['linux_x86_64']
    >>> get_replace_platforms('manylinux1_i686')
    ['linux_i686']

    """
    return _PLATFORM_REPLACEMENT_MAP.get(name, [])


from .external_references import lddtree_external_references
from .versioned_symbols import versioned_symbols_policy

__all__ = ['lddtree_external_references', 'versioned_symbols_policy',
           'load_policies', 'POLICY_PRIORITY_HIGHEST',
           'POLICY_PRIORITY_LOWEST']
