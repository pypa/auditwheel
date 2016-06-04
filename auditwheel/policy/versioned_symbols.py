import logging
from functools import reduce
from typing import Dict, Iterable, Set

from . import load_policies

log = logging.getLogger(__name__)


def versioned_symbols_policy(required_vers: Dict[str, Set[str]]) -> int:
    def policy_is_satisfied(policy_name: str,
                            policy_sym_vers: Dict[str, Set[str]]):
        for symbol_name in (set(required_vers.keys())
                            & set(policy_sym_vers.keys())):
            if not required_vers[name].issubset(policy_sym_vers[name]):
                for symbol in required_vers[name] - policy_sym_vers[name]:
                    log.debug('Package requires %s, incompatible with '
                              'policy %s which requires %s', symbol,
                              policy_name, policy_sym_vers[name])
                return False
        return True

    matching_policies = []  # type: List[int]
    for p in load_policies():
        policy_sym_vers = {
            sym_name: {sym_name + '_' + version for version in versions}
            for sym_name, versions in p['symbol_versions'].items()
        }
        if policy_is_satisfied(p['name'], policy_sym_vers):
            matching_policies.append(p['priority'])

    if len(matching_policies) == 0:
        # the base policy (generic linux) should always match
        raise RuntimeError('Internal error')

    return max(matching_policies)
