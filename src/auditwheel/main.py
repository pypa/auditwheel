from __future__ import annotations

import argparse
import logging
import pathlib
import sys
from importlib import metadata
from pathlib import Path

import auditwheel
from auditwheel import main_lddtree, main_repair, main_show


def main() -> int | None:
    if sys.platform != "linux":
        print("Error: This tool only supports Linux")
        return 1

    location = pathlib.Path(auditwheel.__file__).parent.resolve()
    version = "auditwheel {} installed at {} (python {}.{})".format(
        metadata.version("auditwheel"), location, *sys.version_info
    )

    p = argparse.ArgumentParser(description="Cross-distro Python wheels.")
    p.set_defaults(prog=Path(sys.argv[0]).name)
    p.add_argument("-V", "--version", action="version", version=version)
    p.add_argument(
        "-v",
        "--verbose",
        action="count",
        dest="verbose",
        default=0,
        help="Give more output. Option is additive",
    )
    sub_parsers = p.add_subparsers(metavar="command", dest="cmd")

    main_show.configure_parser(sub_parsers)
    main_repair.configure_parser(sub_parsers)
    main_lddtree.configure_subparser(sub_parsers)

    args = p.parse_args()

    logging.disable(logging.NOTSET)
    if args.verbose >= 1:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if not hasattr(args, "func"):
        p.print_help()
        return None
    result: int | None = args.func(args, p)
    return result
