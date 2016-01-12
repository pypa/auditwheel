import os
import csv
import json
import logging
from collections import defaultdict
from typing import Iterator, Tuple
from wheel.util import native

from .genericpkgctx import InGenericPkgCtx
from .readelf import (elf_file_filter, elf_inspect_dynamic,
                      elf_find_versioned_symbols)
from .policy import elf_exteral_referenence_policy, versioned_symbols_policy
log = logging.getLogger(__name__)


def configure_parser(sub_parsers):
    p = sub_parsers.add_parser(
        'listdeps',
        help="List shared library dependencies of a wheel",
        description="List shared library dependencies of a wheel")
    p.add_argument('wheel', help='Path to wheel file')
    p.set_defaults(func=execute)


def execute(args, p):
    with InGenericPkgCtx(args.wheel) as ctx:
        external_refs = defaultdict(lambda: {})
        versioned_symbols = defaultdict(lambda: set())

        for fn, elf in elf_file_filter(ctx.iter_files()):
            log.info('processing so: %s', fn)
            external_refs.update(elf_exteral_referenence_policy(fn, elf))
            for key, value in elf_find_versioned_symbols(elf):
                versioned_symbols[key].add(value)

    log.debug(json.dumps(external_refs, indent=4))

    print('\n%s references the following external '
          'shared library dependencies:' % os.path.basename(args.wheel))
    print(json.dumps(
        {k: {'note': v['note'],
             'path': v['path']}
         for k, v in external_refs.items() if v['note'] is not 'whitelist'},
        indent=4))

    versioned_symbols = {k: sorted(v) for k, v in versioned_symbols.items()}
    print('\n%s references the versioned external symbols with '
          'the following versions:' % os.path.basename(args.wheel))
    print(json.dumps(versioned_symbols, indent=4))
    print('\nVersioned symbol policy:')
    print(versioned_symbols_policy(versioned_symbols))
