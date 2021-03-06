import sys
import json
import platform as _platform_module
from collections import defaultdict
from typing import Dict, List, Optional, Set
from os.path import join, dirname, abspath
import logging


logger = logging.getLogger(__name__)

# https://docs.python.org/3/library/platform.html#platform.architecture
bits = 8 * (8 if sys.maxsize > 2 ** 32 else 4)


def get_arch_name() -> str:
    machine = _platform_module.machine()
    if machine not in {'x86_64', 'i686'}:
        return machine
    else:
        return {64: 'x86_64', 32: 'i686'}[bits]


_ARCH_NAME = get_arch_name()


def _validate_pep600_compliance(policies) -> None:
    symbol_versions: Dict[str, Dict[str, Set[str]]] = {}
    lib_whitelist: Set[str] = set()
    for policy in sorted(policies, key=lambda x: x['priority'], reverse=True):
        if policy['name'] == 'linux':
            continue
        if not lib_whitelist.issubset(set(policy['lib_whitelist'])):
            diff = lib_whitelist - set(policy["lib_whitelist"])
            raise ValueError(
                'Invalid "policy.json" file. Missing whitelist libraries in '
                f'"{policy["name"]}" compared to previous policies: {diff}'
            )
        lib_whitelist.update(policy['lib_whitelist'])
        for arch in policy['symbol_versions'].keys():
            symbol_versions_arch = symbol_versions.get(arch, defaultdict(set))
            for prefix in policy['symbol_versions'][arch].keys():
                policy_symbol_versions = set(
                    policy['symbol_versions'][arch][prefix])
                if not symbol_versions_arch[prefix].issubset(
                        policy_symbol_versions):
                    diff = symbol_versions_arch[prefix] - \
                           policy_symbol_versions
                    raise ValueError(
                        'Invalid "policy.json" file. Symbol versions missing '
                        f'in "{policy["name"]}_{arch}" for "{prefix}" '
                        f'compared to previous policies: {diff}'
                    )
                symbol_versions_arch[prefix].update(
                    policy['symbol_versions'][arch][prefix])
            symbol_versions[arch] = symbol_versions_arch


with open(join(dirname(abspath(__file__)), 'policy.json')) as f:
    _POLICIES = []
    _policies_temp = json.load(f)
    _validate_pep600_compliance(_policies_temp)
    for _p in _policies_temp:
        if _ARCH_NAME in _p['symbol_versions'].keys() or _p['name'] == 'linux':
            if _p['name'] != 'linux':
                _p['symbol_versions'] = _p['symbol_versions'][_ARCH_NAME]
            _p['name'] = _p['name'] + '_' + _ARCH_NAME
            _p['aliases'] = [alias + '_' + _ARCH_NAME
                             for alias in _p['aliases']]
            _POLICIES.append(_p)

POLICY_PRIORITY_HIGHEST = max(p['priority'] for p in _POLICIES)
POLICY_PRIORITY_LOWEST = min(p['priority'] for p in _POLICIES)


def load_policies():
    return _POLICIES


def _load_policy_schema():
    with open(join(dirname(abspath(__file__)), 'policy-schema.json')) as f:
        schema = json.load(f)
    return schema


def get_policy_by_name(name: str) -> Optional[Dict]:
    matches = [p for p in _POLICIES
               if p['name'] == name or name in p['aliases']]
    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise RuntimeError('Internal error. Policies should be unique')
    return matches[0]


def get_policy_name(priority: int) -> Optional[str]:
    matches = [p['name'] for p in _POLICIES if p['priority'] == priority]
    if len(matches) == 0:
        return None
    if len(matches) > 1:
        raise RuntimeError('Internal error. priorities should be unique')
    return matches[0]


def get_priority_by_name(name: str) -> Optional[int]:
    policy = get_policy_by_name(name)
    return None if policy is None else policy['priority']


def get_replace_platforms(name: str) -> List[str]:
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
    if name.startswith('linux'):
        return []
    if name.startswith('manylinux_'):
        return ['linux_' + '_'.join(name.split('_')[3:])]
    return ['linux_' + '_'.join(name.split('_')[1:])]


# These have to be imported here to avoid a circular import.
from .external_references import lddtree_external_references  # noqa
from .versioned_symbols import versioned_symbols_policy  # noqa

__all__ = ['lddtree_external_references', 'versioned_symbols_policy',
           'load_policies', 'POLICY_PRIORITY_HIGHEST',
           'POLICY_PRIORITY_LOWEST']
