import json
from os.path import join, dirname, abspath

with open(join(dirname(abspath(__file__)), 'policy.json')) as f:
    _POLICY = json.load(f)

POLICY_PRIORITY_HIGHEST = max(p['priority'] for p in _POLICY)
POLICY_PRIORITY_LOWEST = max(p['priority'] for p in _POLICY)


def load_policy():
    return _POLICY


def _load_policy_schema():
    with open(join(dirname(abspath(__file__)), 'policy-schema.json')) as f:
        schema = json.load(f)
    return schema

from .external_references import elf_exteral_referenence_policy
from .versioned_symbols import versioned_symbols_policy

__all__ = ['elf_exteral_referenence_policy', 'versioned_symbols_policy',
           'load_policy', 'POLICY_PRIORITY_HIGHEST', 'POLICY_PRIORITY_LOWEST']
           


