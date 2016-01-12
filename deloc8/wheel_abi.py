import json
import logging
from collections import defaultdict

from .genericpkgctx import InGenericPkgCtx
from .readelf import (elf_file_filter, elf_find_versioned_symbols)
from .policy import (elf_exteral_referenence_policy, versioned_symbols_policy,
                     get_policy_name, POLICY_PRIORITY_LOWEST)
log = logging.getLogger(__name__)


def analyze_wheel_abi(wheel_fn: str):
    external_refs = defaultdict(lambda: {})
    versioned_symbols = defaultdict(lambda: set())
    with InGenericPkgCtx(wheel_fn) as ctx:
        for fn, elf in elf_file_filter(ctx.iter_files()):
            log.info('processing so: %s', fn)
            external_refs.update(elf_exteral_referenence_policy(fn, elf))
            for key, value in elf_find_versioned_symbols(elf):
                versioned_symbols[key].add(value)

    versioned_symbols = {k: sorted(v) for k, v in versioned_symbols.items()}
    log.debug('external referene info')
    log.debug(json.dumps(external_refs, indent=4))

    symbol_policy = versioned_symbols_policy(versioned_symbols)
    ref_policy = min(
        (e['policy_priority'] for e in external_refs.values()),
        default=POLICY_PRIORITY_LOWEST)

    ref_tag = get_policy_name(ref_policy)
    sym_tag = get_policy_name(symbol_policy)
    overall_tag = get_policy_name(min(symbol_policy, ref_policy))

    return overall_tag, external_refs, ref_tag, versioned_symbols, sym_tag
