import sys
import json
import platform as _platform_module
from typing import Optional
from os.path import join, dirname, abspath

_sys_map = {'linux2': 'linux',
            'linux': 'linux',
            'darwin': 'osx',
            'win32': 'win',
            'openbsd5': 'openbsd'}
non_x86_linux_machines = {'armv6l', 'armv7l', 'ppc64le'}
platform = _sys_map.get(sys.platform, 'unknown')
bits = 8 * tuple.__itemsize__
linkage = _platform_module.architecture()[1]

# XXX: this could be weakened. The show command _could_ run on OS X or
# Windows probably, but there's not much reason to inspect foreign package
# that won't run on the platform.
if platform != 'linux':
    print('Error: This tool only supports Linux', file=sys.stderr)
    sys.exit(1)

# if linkage != 'ELF':
#     print(
#         ('Error: This tool only supports platforms that use the ELF '
#          'executable and linker format.'),
#         file=sys.stderr)
#     sys.exit(1)

if _platform_module.machine() in non_x86_linux_machines:
    arch_name = machine()
else:
    arch_name = {64: 'x86_64', 32: '_i386'}[bits]

with open(join(dirname(abspath(__file__)), 'policy.json')) as f:
    _POLICIES = json.load(f)
    for p in _POLICIES:
        p['name'] = p['name'] + '_' + arch_name

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
        raise RuntimeError('Internal error. priorities should be unique')
    return matches[0]


from .external_references import elf_exteral_referenences
from .versioned_symbols import versioned_symbols_policy

__all__ = ['elf_exteral_referenences', 'versioned_symbols_policy',
           'load_policy', 'POLICY_PRIORITY_HIGHEST', 'POLICY_PRIORITY_LOWEST']
