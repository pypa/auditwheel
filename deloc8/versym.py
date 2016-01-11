import logging
from functools import reduce
from collections import defaultdict, OrderedDict
from distutils.version import StrictVersion as Version
from typing import Dict, Sequence, TypeVar, Optional
log = logging.getLogger(__name__)
K = TypeVar('K')
V = TypeVar('V')

SYMBOL_VERSION_POLCIES = OrderedDict(((
    'manylinux',
    # determined by running readelf -V on the relevent
    # files on a CentOS 5 machine, and looking at
    # the Version definition section.
    {
        'GLIBC': Version('2.5'),  # libc.so.6
        'CXXABI': Version('3.4.8'),  # libstdc++.so.6
        'GLIBCXX': Version('1.3.1'),  # libstdc++.so.6
        'GCC': Version('4.2.0')  # libgcc_s.so.1
    }),
))


def check_versioned_symbols_policy(data: Dict[str, Sequence[str]]) -> str:
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

    def policy_is_satisfied(tag: str, policy: Dict[str, Version]):
        for name in (set(max_required_ver.keys()) & set(policy.keys())):
            if max_required_ver[name] > policy[name]:
                log.debug('Package requires %s_%s, incompatible with policy '
                          '%s which requires <= %s_%s', name,
                          max_required_ver[name], tag, name, policy[name])
                return False
        return True

    # if nothing matches, the fallback is 'linux'
    matching_policy = 'linux'
    for tag, policy in SYMBOL_VERSION_POLCIES.items():
        if policy_is_satisfied(tag, policy):
            matching_policy = tag
            break

    return matching_policy


if __name__ == '__main__':
    data = {
        "libm.so.6": [
            "GLIBC_2.2.5"
        ],
        "ld-linux-x86-64.so.2": [
            "GLIBC_2.3"
        ],
        "libpthread.so.0": [
            "GLIBC_2.2.5"
        ],
        "libc.so.6": [
            "GLIBC_2.2.5", "GLIBC_2.3"
        ]
    }
    assert check_versioned_symbols_policy(data) == 'manylinux'
