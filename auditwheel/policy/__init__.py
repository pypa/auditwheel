import sys
import json
import platform as _platform_module
from typing import Optional
from os.path import join, dirname, abspath
import logging


logger = logging.getLogger(__name__)

# https://docs.python.org/3/library/platform.html#platform.architecture
bits = 8 * (8 if sys.maxsize > 2 ** 32 else 4)


_PLATFORM_REPLACEMENT_MAP = {}
for _policy in {'manylinux1', 'manylinux2010'}:
    for _arch in {'x86_64', 'i686'}:
        _key = '{}_{}'.format(_policy, _arch)
        _value = 'linux_{}'.format(_arch)
        _PLATFORM_REPLACEMENT_MAP[_key] = [_value]

for _policy in {'manylinux2014'}:
    for _arch in {
        'x86_64', 'i686', 'aarch64', 'armv7l', 'ppc64', 'ppc64le', 's390x'
    }:
        _key = '{}_{}'.format(_policy, _arch)
        _value = 'linux_{}'.format(_arch)
        _PLATFORM_REPLACEMENT_MAP[_key] = [_value]


def get_arch_name():
    machine = _platform_module.machine()
    if machine not in {'x86_64', 'i686'}:
        return machine
    else:
        return {64: 'x86_64', 32: 'i686'}[bits]


_ARCH_NAME = get_arch_name()


with open(join(dirname(abspath(__file__)), 'policy.json')) as f:
    _POLICIES = []
    _policies_temp = json.load(f)
    for _p in _policies_temp:
        _name = _p['name'] + '_' + _ARCH_NAME
        if _name in _PLATFORM_REPLACEMENT_MAP or _name.startswith('linux'):
            _p['name'] = _name
            _POLICIES.append(_p)

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


# These have to be imported here to avoid a circular import.
from .external_references import lddtree_external_references  # noqa
from .versioned_symbols import versioned_symbols_policy  # noqa

__all__ = ['lddtree_external_references', 'versioned_symbols_policy',
           'load_policies', 'POLICY_PRIORITY_HIGHEST',
           'POLICY_PRIORITY_LOWEST']
