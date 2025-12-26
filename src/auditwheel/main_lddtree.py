from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

logger = logging.getLogger(__name__)


def configure_subparser(sub_parsers) -> None:  # type: ignore[no-untyped-def]
    help = "Analyze a single ELF file (similar to ``ldd``)."
    p = sub_parsers.add_parser("lddtree", help=help, description=help)
    p.add_argument("file", help="Path to .so file")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace, p: argparse.ArgumentParser) -> int:  # noqa: ARG001
    from . import json
    from .lddtree import ldd

    logger.info(json.dumps(ldd(args.file)))
    return 0
