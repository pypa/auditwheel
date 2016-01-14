import os
import sys
import logging
import argparse
import pkg_resources

from . import main_show
from . import main_lddtree
# from . import main_fixup


def main():
    dist = pkg_resources.get_distribution('deloc8')
    version = 'deloc8 %s installed at %s (python %s)' % (
        dist.version, dist.location, sys.version[:3])

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
    # main_fixup.configure_parser(sub_parsers)
    main_lddtree.configure_subparser(sub_parsers)

    args = p.parse_args()

    logging.disable(logging.NOTSET)
    if args.verbose >= 2:
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose == 1:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARN)

    if not hasattr(args, 'func'):
        p.print_help()
        return

    try:
        args.func(args, p)
    except:
        # TODO(rmcgibbo): nice message
        raise
