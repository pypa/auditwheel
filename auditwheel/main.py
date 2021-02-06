import os
import sys
import logging
import argparse
import pkg_resources
from typing import Optional

from . import main_show
from . import main_addtag
from . import main_lddtree
from . import main_repair


def main() -> Optional[int]:
    if sys.platform != 'linux':
        print('Error: This tool only supports Linux')
        return 1

    dist = pkg_resources.get_distribution('auditwheel')
    version = 'auditwheel {} installed at {} (python {}.{})'.format(
        dist.version, dist.location, *sys.version_info)

    p = argparse.ArgumentParser(description='Cross-distro Python wheels.')
    p.set_defaults(prog=os.path.basename(sys.argv[0]))
    p.add_argument('-V', '--version', action='version', version=version)
    p.add_argument("-v",
                   "--verbose",
                   action='count',
                   dest='verbose',
                   default=0,
                   help='Give more output. Option is additive')
    sub_parsers = p.add_subparsers(metavar='command', dest='cmd')

    main_show.configure_parser(sub_parsers)
    main_addtag.configure_parser(sub_parsers)
    main_repair.configure_parser(sub_parsers)
    main_lddtree.configure_subparser(sub_parsers)

    args = p.parse_args()

    logging.disable(logging.NOTSET)
    if args.verbose >= 1:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if not hasattr(args, 'func'):
        p.print_help()
        return None

    rval = args.func(args, p)

    return rval
