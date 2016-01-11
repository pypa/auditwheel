import os
import glob
import json
import logging
from collections import defaultdict
from typing import Iterable, Tuple

from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError

from .wheeltools import InWheelCtx
from .readelf import (elf_inspect_dynamic,
                      locate_with_ldpaths,
                      is_whitelisted,
                      locate_with_ld_so,
                      load_ld_library_path)

FilePath = str
log = logging.getLogger(__name__)


def configure_parser(sub_parsers):
    p = sub_parsers.add_parser(
        'listdeps',
        description="List shard library dependencies of a wheel")
    p.add_argument('wheel', help='Path to wheel file')
    p.set_defaults(func=execute)


def wheel_files(wheel_path='.'):
    record_fn = glob.glob(
        os.path.join(wheel_path, '*.dist-info/RECORD'))[0]
    with open(record_fn) as f:
        for line in f:
            yield line.split(',')[0]


def elf_file_filter(paths : Iterable[FilePath]) -> Iterable[Tuple[FilePath, ELFFile]]:
    for path in paths:
        if path.endswith('.py'):
            continue
        else:
            try:
                with open(path, 'rb') as f:
                    candidate = ELFFile(f)
                    yield path, candidate
            except ELFError:
                # not an elf file
                continue



def execute(args, p):
    ld_library_path = load_ld_library_path()

    with InWheelCtx(args.wheel) as ctx:
        external = defaultdict(lambda: {})

        for fn, elf in elf_file_filter(wheel_files()):
            log.info('processing so: %s', fn)
                

            sonames, rpath = elf_inspect_dynamic(elf)
            for soname in sonames:
                if is_whitelisted(soname):
                    log.debug('whitelisted: %s', soname)
                    continue

                resolved = locate_with_ldpaths(soname, rpath)
                if resolved is not None:
                    log.debug('resolved via rpath: %s', soname)
                    external[fn][soname] = resolved
                    continue

                resolved = locate_with_ldpaths(soname, ld_library_path)
                if resolved is not None:
                    log.debug('resolved via ld_library_path: %s', soname)
                    external[fn][soname] = resolved
                    continue

                resolved = locate_with_ld_so(soname)
                if resolved is not None:
                    log.debug('resolved via ld.so.conf: %s', soname)
                    external[fn][soname] = resolved
                    continue

                raise ValueError(soname)

    print('%s contains the following external dependencies:' % os.path.basename(args.wheel))
    print(json.dumps(external, indent=4))
