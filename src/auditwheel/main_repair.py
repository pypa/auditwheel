from __future__ import annotations

import argparse
import logging
import shutil
import zlib
from pathlib import Path
from typing import Any

from auditwheel.architecture import Architecture
from auditwheel.error import NonPlatformWheelError, WheelToolsError
from auditwheel.libc import Libc
from auditwheel.patcher import Patchelf
from auditwheel.policy import WheelPolicies
from auditwheel.tools import EnvironmentDefault
from auditwheel.wheeltools import get_wheel_architecture, get_wheel_libc

logger = logging.getLogger(__name__)


def configure_parser(sub_parsers: Any) -> None:  # noqa: ANN401
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
    help_ = """Vendor in external shared library dependencies of a wheel.
If multiple wheels are specified, an error processing one
wheel will abort processing of subsequent wheels.
"""
    parser = sub_parsers.add_parser(
        "repair",
        help=help_,
        description=help_,
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
        help="Strip symbols in the resulting wheel",
        default=False,
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
    parser.add_argument(
        "--allow-pure-python-wheel",
        dest="ALLOW_PURE_PY_WHEEL",
        action="store_true",
        help="Allow processing of pure Python wheels (no platform-specific binaries) without error",
        default=False,
    )
    parser.set_defaults(func=execute)


def execute(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from auditwheel.repair import repair_wheel
    from auditwheel.wheel_abi import analyze_wheel_abi

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
        is_pure_python = False
        try:
            arch = get_wheel_architecture(wheel_filename)
            if requested_architecture is not None and requested_architecture != arch:
                msg = (
                    f"can't repair wheel {wheel_filename} with {arch.value} architecture to a "
                    f"wheel targeting {requested_architecture.value}"
                )
                parser.error(msg)
        except (WheelToolsError, NonPlatformWheelError) as e:
            logger.warning(
                "The architecture could not be deduced from the wheel filename",
            )
            is_pure_python = isinstance(e, NonPlatformWheelError)

        try:
            libc = get_wheel_libc(wheel_filename)
        except WheelToolsError:
            logger.debug("The libc could not be deduced from the wheel filename")
            libc = None

        if plat_base.startswith("manylinux"):
            if libc is None:
                libc = Libc.GLIBC
            if libc != Libc.GLIBC:
                msg = (
                    f"can't repair wheel {wheel_filename} with {libc.name} libc to a wheel "
                    "targeting GLIBC"
                )
                parser.error(msg)
        elif plat_base.startswith("musllinux"):
            if libc is None:
                libc = Libc.MUSL
            if libc != Libc.MUSL:
                msg = (
                    f"can't repair wheel {wheel_filename} with {libc.name} libc to a wheel "
                    "targeting MUSL"
                )
                parser.error(msg)

        logger.info("Repairing %s", wheel_filename)

        if not wheel_dir.exists():
            wheel_dir.mkdir(parents=True)

        try:
            wheel_abi = analyze_wheel_abi(
                libc,
                arch,
                wheel_file,
                exclude,
                disable_isa_ext_check=args.DISABLE_ISA_EXT_CHECK,
                allow_graft=True,
                requested_policy_base_name=plat_base,
            )
        except NonPlatformWheelError as e:
            logger.info(e.message)
            if is_pure_python and args.ALLOW_PURE_PY_WHEEL:
                dest_fname = wheel_dir / wheel_file.name
                if not dest_fname.is_file() or not dest_fname.samefile(wheel_file):
                    shutil.copy2(wheel_file, dest_fname)
                # process next wheel
                continue
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

        patcher = Patchelf()
        out_wheel = repair_wheel(
            wheel_abi,
            wheel_file,
            abis=abis,
            lib_sdir=args.LIB_SDIR,
            out_dir=wheel_dir,
            update_tags=args.UPDATE_TAGS,
            patcher=patcher,
            strip=args.STRIP,
            zip_compression_level=args.ZIP_COMPRESSION_LEVEL,
        )

        if out_wheel is not None:
            logger.info("\nFixed-up wheel written to %s", out_wheel)
    return 0
