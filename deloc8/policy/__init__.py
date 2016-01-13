import json
import platform
from typing import Optional
from os.path import join, dirname, abspath
_bitness, _linkage = platform.architecture()

with open(join(dirname(abspath(__file__)), 'policy.json')) as f:
    _POLICIES = json.load(f)
    for p in _POLICIES:
        if _bitness == '32bit':
            p['name'] = p['name'] + '_i386'
        elif _bitness == '64bit':
            p['name'] = p['name'] + '_x86_64'

POLICY_PRIORITY_HIGHEST = max(p['priority'] for p in _POLICIES)
POLICY_PRIORITY_LOWEST = min(p['priority'] for p in _POLICIES)


def load_policies():
    if _linkage != 'ELF':
        raise RuntimeError('Only ELF linkage is supported')
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
