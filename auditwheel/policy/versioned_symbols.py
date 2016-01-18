import logging
from functools import reduce
from pip._vendor.distlib.version import NormalizedVersion as Version
from typing import Dict, Sequence

from . import load_policies

log = logging.getLogger(__name__)


def max_versioned_symbol(data: Dict[str, Sequence[str]]) -> Dict[str, Version]:
    def set_if_greater(d, k, v):
        if (k in d and v > d[k]) or (k not in d):
            d[k] = v

    sym_vers = reduce(set.union, data.values(), set())  # type: Set[str]
    max_required_ver = {}  # type: Dict[str, Version]
    for val in sym_vers:
        if val is not None:
            name, ver = val.split('_')
            set_if_greater(max_required_ver, name, Version(ver))

    log.debug('Required symbol versions: %s', max_required_ver)
    return max_required_ver


def versioned_symbols_policy(max_required_ver: Dict[str, Version]) -> int:
    def policy_is_satisfied(tag: str, policy_sym_vers: Dict[str, Version]):
        for name in (set(max_required_ver.keys())
                     & set(policy_sym_vers.keys())):
            if max_required_ver[name] > policy_sym_vers[name]:
                log.debug('Package requires %s_%s, incompatible with policy '
                          '%s which requires <= %s_%s', name,
                          max_required_ver[name], tag, name,
                          policy_sym_vers[name])
                return False
        return True

    matching_policies = []  # type: List[int]
    for p in load_policies():
        policy_sym_vers = {k: Version(v)
                           for k, v in p['symbol_versions'].items()}
        if policy_is_satisfied(p['name'], policy_sym_vers):
            matching_policies.append(p['priority'])

    if len(matching_policies) == 0:
        # the base policy (generic linux) should always match
        raise RuntimeError('Internal error')

    return max(matching_policies)
