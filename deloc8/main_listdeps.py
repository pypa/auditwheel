import os
import csv
import json
import logging
from collections import defaultdict
from typing import Iterator, Tuple
from wheel.util import native

from .wheeltools import InWheelCtx, iter_wheel_files
from .readelf import (
    elf_file_filter,
    elf_inspect_dynamic,
    elf_find_external_references,
    elf_find_versioned_symbols)


log = logging.getLogger(__name__)


def configure_parser(sub_parsers):
    p = sub_parsers.add_parser(
        'listdeps',
        description="List shard library dependencies of a wheel")
    p.add_argument('wheel', help='Path to wheel file')
    p.set_defaults(func=execute)


def execute(args, p):
    with InWheelCtx(args.wheel) as ctx:
        external_refs = defaultdict(lambda: {})
        versioned_symbols = defaultdict(lambda: set())

        for fn, elf in elf_file_filter(iter_wheel_files()):
            log.info('processing so: %s', fn)
            external_refs.update(elf_find_external_references(fn, elf))
            for key, value in elf_find_versioned_symbols(elf):
                versioned_symbols[key].add(value)


    versioned_symbols = {k: sorted(v) for k, v in versioned_symbols.items()}
    print('\n%s references the following external '
          'shared library dependencies:' %
          os.path.basename(args.wheel))
    print(json.dumps(external_refs, indent=4))
    print()
    print('%s references the versioned external symbols with '
          'the following versions:' % os.path.basename(args.wheel))
    print(json.dumps(versioned_symbols, indent=4))
    
