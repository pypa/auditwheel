from __future__ import annotations

import argparse
import logging

from auditwheel.policy import WheelPolicies

logger = logging.getLogger(__name__)


def configure_parser(sub_parsers) -> None:  # type: ignore[no-untyped-def]
    help = "Audit a wheel for external shared library dependencies."
    p = sub_parsers.add_parser("show", help=help, description=help)
    p.add_argument("WHEEL_FILE", help="Path to wheel file.")
    p.add_argument(
        "--disable-isa-ext-check",
        dest="DISABLE_ISA_EXT_CHECK",
        action="store_true",
        help="Do not check for extended ISA compatibility (e.g. x86_64_v2)",
        default=False,
    )
    p.set_defaults(func=execute)


def printp(text: str) -> None:
    from textwrap import wrap

    print()
    print("\n".join(wrap(text, break_long_words=False, break_on_hyphens=False)))


def execute(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from os.path import basename, isfile

    from . import json
    from .wheel_abi import NonPlatformWheel, analyze_wheel_abi

    wheel_policy = WheelPolicies()

    fn = basename(args.WHEEL_FILE)

    if not isfile(args.WHEEL_FILE):
        parser.error(f"cannot access {args.WHEEL_FILE}. No such file")

    try:
        winfo = analyze_wheel_abi(
            wheel_policy, args.WHEEL_FILE, frozenset(), args.DISABLE_ISA_EXT_CHECK
        )
    except NonPlatformWheel as e:
        logger.info(e.message)
        return 1

    libs_with_versions = [
        f"{k} with versions {v}" for k, v in winfo.versioned_symbols.items()
    ]

    printp(
        f'{fn} is consistent with the following platform tag: "{winfo.overall_tag}".'
    )

    if (
        wheel_policy.get_priority_by_name(winfo.pyfpe_tag)
        < wheel_policy.priority_highest
    ):
        printp(
            "This wheel uses the PyFPE_jbuf function, which is not compatible with the"
            " manylinux1 tag. (see https://www.python.org/dev/peps/pep-0513/"
            "#fpectl-builds-vs-no-fpectl-builds)"
        )
        if args.verbose < 1:
            return 0

    if wheel_policy.get_priority_by_name(winfo.ucs_tag) < wheel_policy.priority_highest:
        printp(
            "This wheel is compiled against a narrow unicode (UCS2) "
            "version of Python, which is not compatible with the "
            "manylinux1 tag."
        )
        if args.verbose < 1:
            return 0

    if (
        wheel_policy.get_priority_by_name(winfo.machine_tag)
        < wheel_policy.priority_highest
    ):
        printp("This wheel depends on unsupported ISA extensions.")
        if args.verbose < 1:
            return 0

    if len(libs_with_versions) == 0:
        printp(
            "The wheel references no external versioned symbols from "
            "system-provided shared libraries."
        )
    else:
        printp(
            "The wheel references external versioned symbols in these "
            f"system-provided shared libraries: {', '.join(libs_with_versions)}"
        )

    if wheel_policy.get_priority_by_name(winfo.sym_tag) < wheel_policy.priority_highest:
        printp(
            f'This constrains the platform tag to "{winfo.sym_tag}". '
            "In order to achieve a more compatible tag, you would "
            "need to recompile a new wheel from source on a system "
            "with earlier versions of these libraries, such as "
            "a recent manylinux image."
        )
        if args.verbose < 1:
            return 0

    libs = winfo.external_refs[
        wheel_policy.get_policy_name(wheel_policy.priority_lowest)
    ]["libs"]
    if len(libs) == 0:
        printp("The wheel requires no external shared libraries! :)")
    else:
        printp("The following external shared libraries are required by the wheel:")
        print(json.dumps(dict(sorted(libs.items()))))

    for p in sorted(wheel_policy.policies, key=lambda p: p["priority"]):
        if p["priority"] > wheel_policy.get_priority_by_name(winfo.overall_tag):
            libs = winfo.external_refs[p["name"]]["libs"]
            if len(libs):
                printp(
                    f'In order to achieve the tag platform tag "{p["name"]}" '
                    "the following shared library dependencies "
                    "will need to be eliminated:"
                )
                printp(", ".join(sorted(libs.keys())))
            blacklist = winfo.external_refs[p["name"]]["blacklist"]
            if len(blacklist):
                printp(
                    f'In order to achieve the tag platform tag "{p["name"]}" '
                    "the following black-listed symbol dependencies "
                    "will need to be eliminated:"
                )
                for key in sorted(blacklist.keys()):
                    printp(f"From {key}: " + ", ".join(sorted(blacklist[key])))
    return 0
