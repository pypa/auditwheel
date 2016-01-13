import argparse
import logging
from . import main_versym
from . import main_listdeps
from . import main_lddtree
from . import main_fixup


def main():
    p = argparse.ArgumentParser()
    p.add_argument('-V',
                   '--version',
                   help='Show version and exit.',
                   action='store_true')
    p.add_argument("-v",
                   "--verbose",
                   action='count',
                   dest='verbose',
                   default=0,
                   help='Give more output. Option is additive')
    sub_parsers = p.add_subparsers(metavar='command', dest='cmd')

    main_listdeps.configure_parser(sub_parsers)
    main_versym.configure_parser(sub_parsers)
    main_fixup.configure_parser(sub_parsers)
    main_lddtree.configure_subparser(sub_parsers)

    args = p.parse_args()
    if args.version:
        return show_version()

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


def show_version():
    import sys
    import pkg_resources
    dist = pkg_resources.get_distribution('deloc8')
    print('deloc8 %s from %s (python %s)' % (dist.version, dist.location,
                                             sys.version[:3]))
    return 1


if __name__ == '__main__':
    main()
