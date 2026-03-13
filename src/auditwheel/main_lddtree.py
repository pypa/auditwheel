from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from auditwheel import main_options

if TYPE_CHECKING:
    import argparse

logger = logging.getLogger(__name__)


def configure_subparser(sub_parsers: Any) -> None:  # noqa: ANN401
    help_ = "Analyze a single ELF file (similar to ``ldd``)."
    p = sub_parsers.add_parser("lddtree", help=help_, description=help_)
    p.add_argument("file", type=Path, help="Path to .so file")
    main_options.ldpaths(p)
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace, p: argparse.ArgumentParser) -> int:  # noqa: ARG001
    from auditwheel import json
    from auditwheel.lddtree import ld_paths_from_arg, ldd

    logger.info(json.dumps(ldd(args.file, ldpaths=ld_paths_from_arg(args.LDPATHS))))
    return 0
