"""Options shared between multiple subcommands."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import ArgumentParser


def disable_isa_check(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--disable-isa-ext-check",
        dest="DISABLE_ISA_EXT_CHECK",
        action="store_true",
        help="Do not check for extended ISA compatibility (e.g. x86_64_v2)",
        default=False,
    )


def allow_pure_python_wheel(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--allow-pure-python-wheel",
        dest="ALLOW_PURE_PY_WHEEL",
        action="store_true",
        help="Allow processing of pure Python wheels (no platform-specific binaries) without error",
        default=False,
    )


def ldpaths(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--ldpaths",
        dest="LDPATHS",
        help="Colon-delimited list of directories to search for external libraries. "
        "This replaces the default list; to add to this list, set the environment "
        "variable AUDITWHEEL_LD_LIBRARY_PATH.",
    )
