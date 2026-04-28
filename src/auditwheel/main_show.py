from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import argparse

    from auditwheel.wheel_abi import WheelAbIInfo

logger = logging.getLogger(__name__)


def configure_parser(sub_parsers: Any) -> None:  # noqa: ANN401
    help_ = "Audit a wheel for external shared library dependencies."
    p = sub_parsers.add_parser("show", help=help_, description=help_)
    p.add_argument("WHEEL_FILE", type=Path, help="Path to wheel file.")
    p.add_argument(
        "--disable-isa-ext-check",
        dest="DISABLE_ISA_EXT_CHECK",
        action="store_true",
        help="Do not check for extended ISA compatibility (e.g. x86_64_v2)",
        default=False,
    )
    p.add_argument(
        "--allow-pure-python-wheel",
        dest="ALLOW_PURE_PY_WHEEL",
        action="store_true",
        help="Allow processing of pure Python wheels (no platform-specific binaries) without error",
        default=False,
    )
    p.add_argument(
        "--json",
        dest="JSON",
        action="store_true",
        default=False,
        help="Output results in JSON format",
    )
    p.set_defaults(func=execute)


def printp(text: str) -> None:
    from textwrap import wrap

    print()
    print("\n".join(wrap(text, break_long_words=False, break_on_hyphens=False)))


def _output_json(fn: str, winfo: WheelAbIInfo) -> None:
    from auditwheel import json

    policies = winfo.policies
    libs = winfo.external_refs[policies.lowest.name].libs

    policy_upgrades: dict[str, dict[str, Any]] = {}
    for p in policies:
        if p > winfo.overall_policy:
            entry: dict[str, Any] = {}
            p_libs = winfo.external_refs[p.name].libs
            if len(p_libs):
                entry["libs_to_eliminate"] = sorted(p_libs.keys())
            blacklist = winfo.external_refs[p.name].blacklist
            if len(blacklist):
                entry["blacklisted_symbols"] = {k: sorted(v) for k, v in sorted(blacklist.items())}
            if entry:
                policy_upgrades[p.name] = entry

    result: dict[str, Any] = {
        "version": 1,
        "wheel": fn,
        "pure": False,
        "overall_tag": winfo.overall_policy.name,
        "sym_tag": winfo.sym_policy.name,
        "pyfpe": winfo.pyfpe_policy == policies.linux,
        "ucs2": winfo.ucs_policy == policies.linux,
        "unsupported_isa": winfo.machine_policy == policies.linux,
        "versioned_symbols": {k: sorted(v) for k, v in sorted(winfo.versioned_symbols.items())},
        "external_libs": {str(k): str(v) if v else None for k, v in sorted(libs.items())},
        "policy_upgrades": policy_upgrades,
    }

    print(json.dumps(result))


def execute(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from auditwheel import json
    from auditwheel.error import NonPlatformWheelError, WheelToolsError
    from auditwheel.wheel_abi import analyze_wheel_abi
    from auditwheel.wheeltools import get_wheel_architecture, get_wheel_libc

    wheel_file: Path = args.WHEEL_FILE
    fn = wheel_file.name

    if not wheel_file.is_file():
        parser.error(f"cannot access {wheel_file}. No such file")

    fn = wheel_file.name
    is_pure_python = False
    try:
        arch = get_wheel_architecture(fn)
    except (WheelToolsError, NonPlatformWheelError) as e:
        logger.warning("The architecture could not be deduced from the wheel filename")
        is_pure_python = isinstance(e, NonPlatformWheelError)
        arch = None

    try:
        libc = get_wheel_libc(fn)
    except WheelToolsError:
        logger.debug("The libc could not be deduced from the wheel filename")
        libc = None

    try:
        winfo = analyze_wheel_abi(
            libc,
            arch,
            wheel_file,
            frozenset(),
            disable_isa_ext_check=args.DISABLE_ISA_EXT_CHECK,
            allow_graft=False,
        )
    except NonPlatformWheelError as e:
        logger.info("%s", e.message)
        if is_pure_python and args.ALLOW_PURE_PY_WHEEL:
            if args.JSON:
                print(json.dumps({"version": 1, "wheel": fn, "pure": True}))
            return 0
        if args.JSON:
            print(json.dumps({"version": 1, "wheel": fn, "error": e.message}))
        return 1

    if args.JSON:
        _output_json(fn, winfo)
        return 0

    policies = winfo.policies

    libs_with_versions = [f"{k} with versions {v}" for k, v in winfo.versioned_symbols.items()]

    printp(
        f'{fn} is consistent with the following platform tag: "{winfo.overall_policy.name}".',
    )

    if winfo.pyfpe_policy == policies.linux:
        printp(
            "This wheel uses the PyFPE_jbuf function, which is not compatible with the"
            " manylinux/musllinux tags. (see https://www.python.org/dev/peps/pep-0513/"
            "#fpectl-builds-vs-no-fpectl-builds)",
        )
        if args.verbose < 1:
            return 0

    if winfo.ucs_policy == policies.linux:
        printp(
            "This wheel is compiled against a narrow unicode (UCS2) "
            "version of Python, which is not compatible with the "
            "manylinux/musllinux tags.",
        )
        if args.verbose < 1:
            return 0

    if winfo.machine_policy == policies.linux:
        printp("This wheel depends on unsupported ISA extensions.")
        if args.verbose < 1:
            return 0

    if len(libs_with_versions) == 0:
        printp(
            "The wheel references no external versioned symbols from "
            "system-provided shared libraries.",
        )
    else:
        printp(
            "The wheel references external versioned symbols in these "
            f"system-provided shared libraries: {', '.join(libs_with_versions)}",
        )

    if winfo.sym_policy < policies.highest:
        printp(
            f'This constrains the platform tag to "{winfo.sym_policy.name}". '
            "In order to achieve a more compatible tag, you would "
            "need to recompile a new wheel from source on a system "
            "with earlier versions of these libraries, such as "
            "a recent manylinux image.",
        )
        if args.verbose < 1:
            return 0

    libs = winfo.external_refs[policies.lowest.name].libs
    if len(libs) == 0:
        printp("The wheel requires no external shared libraries! :)")
    else:
        printp("The following external shared libraries are required by the wheel:")
        print(json.dumps(dict(sorted(libs.items()))))

    for p in policies:
        if p > winfo.overall_policy:
            libs = winfo.external_refs[p.name].libs
            if len(libs):
                printp(
                    f"In order to achieve the tag platform tag {p.name!r} "
                    "the following shared library dependencies "
                    "will need to be eliminated:",
                )
                printp(", ".join(sorted(libs.keys())))
            blacklist = winfo.external_refs[p.name].blacklist
            if len(blacklist):
                printp(
                    f"In order to achieve the tag platform tag {p.name!r} "
                    "the following black-listed symbol dependencies "
                    "will need to be eliminated:",
                )
                for key in sorted(blacklist.keys()):
                    printp(f"From {key}: " + ", ".join(sorted(blacklist[key])))
    return 0
