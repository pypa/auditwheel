from __future__ import annotations

import argparse
import logging
import warnings
import zlib
from pathlib import Path

from auditwheel.architecture import Architecture
from auditwheel.error import NonPlatformWheel, WheelToolsError
from auditwheel.libc import Libc
from auditwheel.patcher import Patchelf
from auditwheel.wheeltools import get_wheel_architecture, get_wheel_libc

from .policy import WheelPolicies
from .repair import StripLevel
from .tools import EnvironmentDefault

logger = logging.getLogger(__name__)


def configure_parser(sub_parsers) -> None:  # type: ignore[no-untyped-def]
    policies = WheelPolicies(libc=Libc.detect(), arch=Architecture.detect())
    policy_names = [p.name for p in policies if p != policies.linux]
    policy_names += [alias for p in policies for alias in p.aliases]
    policy_names += ["auto"]
    epilog = """PLATFORMS:
These are the possible target platform tags, as specified by PEP 600.
Note that old, pre-PEP 600 tags are still usable and are listed as aliases
below.
"""
    for p in policies:
        epilog += f"- {p.name}"
        if len(p.aliases) > 0:
            epilog += f" (aliased by {', '.join(p.aliases)})"
        epilog += "\n"
    help = """Vendor in external shared library dependencies of a wheel.
If multiple wheels are specified, an error processing one
wheel will abort processing of subsequent wheels.
"""
    parser = sub_parsers.add_parser(
        "repair",
        help=help,
        description=help,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("WHEEL_FILE", type=Path, help="Path to wheel file.", nargs="+")
    parser.add_argument(
        "-z",
        "--zip-compression-level",
        action=EnvironmentDefault,
        metavar="ZIP_COMPRESSION_LEVEL",
        env="AUDITWHEEL_ZIP_COMPRESSION_LEVEL",
        dest="ZIP_COMPRESSION_LEVEL",
        type=int,
        help="Compress level to be used to create zip file.",
        choices=list(range(zlib.Z_NO_COMPRESSION, zlib.Z_BEST_COMPRESSION + 1)),
        default=zlib.Z_DEFAULT_COMPRESSION,
    )
    parser.add_argument(
        "--plat",
        action=EnvironmentDefault,
        metavar="PLATFORM",
        env="AUDITWHEEL_PLAT",
        dest="PLAT",
        help="Desired target platform. See the available platforms under the "
        'PLATFORMS section below. (default: "auto")',
        choices=policy_names,
        default="auto",
    )
    parser.add_argument(
        "-L",
        "--lib-sdir",
        dest="LIB_SDIR",
        help=('Subdirectory in packages to store copied libraries. (default: ".libs")'),
        default=".libs",
    )
    parser.add_argument(
        "-w",
        "--wheel-dir",
        dest="WHEEL_DIR",
        type=Path,
        help=('Directory to store delocated wheels (default: "wheelhouse/")'),
        default="wheelhouse/",
    )
    parser.add_argument(
        "--no-update-tags",
        dest="UPDATE_TAGS",
        action="store_false",
        help=(
            "Do not update the wheel filename tags and WHEEL info"
            " to match the repaired platform tag."
        ),
        default=True,
    )
    parser.add_argument(
        "--strip",
        dest="STRIP",
        action="store_true",
        help="(DEPRECATED) Strip all symbols in the resulting wheel. Use --strip-level=all instead.",
        default=False,
    )
    parser.add_argument(
        "--strip-level",
        dest="STRIP_LEVEL",
        choices=[level.value for level in StripLevel],
        help="Strip level for symbol processing. Options: none (default), debug (remove debug symbols), unneeded (remove unneeded symbols), all (remove all symbols).",
        default="none",
    )
    parser.add_argument(
        "--collect-debug-symbols",
        dest="COLLECT_DEBUG_SYMBOLS",
        action="store_true",
        help="Extract debug symbols before stripping and create a zip archive.",
        default=False,
    )
    parser.add_argument(
        "--debug-symbols-output",
        dest="DEBUG_SYMBOLS_OUTPUT",
        type=Path,
        help="Output path for debug symbols zip file. Defaults to {wheel_name}_debug_symbols.zip",
        default=None,
    )
    parser.add_argument(
        "--exclude",
        dest="EXCLUDE",
        help="Exclude SONAME from grafting into the resulting wheel "
        "Please make sure wheel metadata reflects your dependencies. "
        "See https://github.com/pypa/auditwheel/pull/411#issuecomment-1500826281 "
        "(can be specified multiple times) "
        "(can contain wildcards, for example libfoo.so.*)",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--only-plat",
        dest="ONLY_PLAT",
        action="store_true",
        help="Do not check for higher policy compatibility",
        default=False,
    )
    parser.add_argument(
        "--disable-isa-ext-check",
        dest="DISABLE_ISA_EXT_CHECK",
        action="store_true",
        help="Do not check for extended ISA compatibility (e.g. x86_64_v2)",
        default=False,
    )
    parser.set_defaults(func=execute)


def execute(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .repair import repair_wheel
    from .wheel_abi import analyze_wheel_abi

    exclude: frozenset[str] = frozenset(args.EXCLUDE)
    wheel_dir: Path = args.WHEEL_DIR.absolute()
    wheel_files: list[Path] = args.WHEEL_FILE

    requested_architecture: Architecture | None = None

    plat_base: str = args.PLAT
    for a in Architecture:
        suffix = f"_{a.value}"
        if plat_base.endswith(suffix):
            plat_base = plat_base[: -len(suffix)]
            requested_architecture = a
            break

    for wheel_file in wheel_files:
        if not wheel_file.is_file():
            parser.error(f"cannot access {wheel_file}. No such file")

        wheel_filename = wheel_file.name
        arch = requested_architecture
        try:
            arch = get_wheel_architecture(wheel_filename)
            if requested_architecture is not None and requested_architecture != arch:
                msg = f"can't repair wheel {wheel_filename} with {arch.value} architecture to a wheel targeting {requested_architecture.value}"
                parser.error(msg)
        except (WheelToolsError, NonPlatformWheel):
            logger.warning(
                "The architecture could not be deduced from the wheel filename"
            )

        try:
            libc = get_wheel_libc(wheel_filename)
        except WheelToolsError:
            logger.debug("The libc could not be deduced from the wheel filename")
            libc = None

        if plat_base.startswith("manylinux"):
            if libc is None:
                libc = Libc.GLIBC
            if libc != Libc.GLIBC:
                msg = f"can't repair wheel {wheel_filename} with {libc.name} libc to a wheel targeting GLIBC"
                parser.error(msg)
        elif plat_base.startswith("musllinux"):
            if libc is None:
                libc = Libc.MUSL
            if libc != Libc.MUSL:
                msg = f"can't repair wheel {wheel_filename} with {libc.name} libc to a wheel targeting MUSL"
                parser.error(msg)

        logger.info("Repairing %s", wheel_filename)

        if not wheel_dir.exists():
            wheel_dir.mkdir(parents=True)

        try:
            wheel_abi = analyze_wheel_abi(
                libc, arch, wheel_file, exclude, args.DISABLE_ISA_EXT_CHECK, True
            )
        except NonPlatformWheel as e:
            logger.info(e.message)
            return 1

        policies = wheel_abi.policies
        if plat_base == "auto":
            if wheel_abi.overall_policy == policies.linux:
                # we're getting 'linux', override
                plat = policies.lowest.name
            else:
                plat = wheel_abi.overall_policy.name
        else:
            plat = f"{plat_base}_{policies.architecture.value}"
        requested_policy = policies.get_policy_by_name(plat)

        if requested_policy > wheel_abi.sym_policy:
            msg = (
                f'cannot repair "{wheel_file}" to "{plat}" ABI because of the '
                "presence of too-recent versioned symbols. You'll need to compile "
                "the wheel on an older toolchain."
            )
            parser.error(msg)

        if requested_policy > wheel_abi.ucs_policy:
            msg = (
                f'cannot repair "{wheel_file}" to "{plat}" ABI because it was '
                "compiled against a UCS2 build of Python. You'll need to compile "
                "the wheel against a wide-unicode build of Python."
            )
            parser.error(msg)

        if requested_policy > wheel_abi.blacklist_policy:
            msg = (
                f'cannot repair "{wheel_file}" to "{plat}" ABI because it '
                "depends on black-listed symbols."
            )
            parser.error(msg)

        if requested_policy > wheel_abi.machine_policy:
            msg = (
                f'cannot repair "{wheel_file}" to "{plat}" ABI because it '
                "depends on unsupported ISA extensions."
            )
            parser.error(msg)

        abis = [requested_policy.name, *requested_policy.aliases]
        if (not args.ONLY_PLAT) and requested_policy < wheel_abi.overall_policy:
            logger.info(
                (
                    "Wheel is eligible for a higher priority tag. "
                    "You requested %s but I have found this wheel is "
                    "eligible for %s."
                ),
                plat,
                wheel_abi.overall_policy.name,
            )
            abis = [
                wheel_abi.overall_policy.name,
                *wheel_abi.overall_policy.aliases,
                *abis,
            ]

        # Handle argument validation and backward compatibility
        if args.STRIP and args.STRIP_LEVEL != "none":
            parser.error("Cannot specify both --strip and --strip-level")

        if args.STRIP:
            warnings.warn(
                "The --strip option is deprecated. Use --strip-level=all instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        if args.COLLECT_DEBUG_SYMBOLS and args.STRIP_LEVEL == "none" and not args.STRIP:
            parser.error(
                "--collect-debug-symbols requires stripping to be enabled. Use --strip-level or --strip."
            )

        strip_level = StripLevel(args.STRIP_LEVEL)

        patcher = Patchelf()
        out_wheel = repair_wheel(
            wheel_abi,
            wheel_file,
            abis=abis,
            lib_sdir=args.LIB_SDIR,
            out_dir=wheel_dir,
            update_tags=args.UPDATE_TAGS,
            patcher=patcher,
            strip=args.STRIP if args.STRIP else None,
            strip_level=strip_level,
            collect_debug_symbols=args.COLLECT_DEBUG_SYMBOLS,
            debug_symbols_output=args.DEBUG_SYMBOLS_OUTPUT,
            zip_compression_level=args.ZIP_COMPRESSION_LEVEL,
        )

        if out_wheel is not None:
            logger.info("\nFixed-up wheel written to %s", out_wheel)
    return 0
