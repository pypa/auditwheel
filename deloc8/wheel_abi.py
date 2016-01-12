import json
import logging
from collections import defaultdict, Mapping, Sequence

from .genericpkgctx import InGenericPkgCtx
from .lddtree import (elf_file_filter, elf_find_versioned_symbols)
from .policy import (elf_exteral_referenences, versioned_symbols_policy,
                     get_policy_name, POLICY_PRIORITY_LOWEST)
log = logging.getLogger(__name__)


def analyze_wheel_abi(wheel_fn: str):
    external_refs = {}  #defaultdict(lambda: {})
    versioned_symbols = defaultdict(lambda: set())
    with InGenericPkgCtx(wheel_fn) as ctx:
        for fn, elf in elf_file_filter(ctx.iter_files()):
            log.info('processing so: %s', fn)
            update(external_refs, elf_exteral_referenences(fn, ctx.path))
            for key, value in elf_find_versioned_symbols(elf):
                versioned_symbols[key].add(value)

    log.info(json.dumps(external_refs, indent=4))
    versioned_symbols = {k: sorted(v) for k, v in versioned_symbols.items()}
    log.debug('external referene info')
    log.debug(json.dumps(external_refs, indent=4))

    symbol_policy = versioned_symbols_policy(versioned_symbols)
    ref_policy = max(
        (e['priority']
         for e in external_refs.values() if len(e['external libs']) == 0),
        default=POLICY_PRIORITY_LOWEST)

    ref_tag = get_policy_name(ref_policy)
    sym_tag = get_policy_name(symbol_policy)
    overall_tag = get_policy_name(min(symbol_policy, ref_policy))

    return overall_tag, external_refs, ref_tag, versioned_symbols, sym_tag


def update(d, u):
    for k, v in u.items():
        if isinstance(v, Mapping):
            r = update(d.get(k, {}), v)
            d[k] = r
        elif isinstance(v, (str, int, float, type(None))):
            d[k] = u[k]
        else:
            raise RuntimeError('!', d, k)
    return d
