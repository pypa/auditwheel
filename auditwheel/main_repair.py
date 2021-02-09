import logging
import os
from os.path import isfile, exists, abspath, basename

from .patcher import Patchelf
from .policy import (load_policies, get_policy_name, get_priority_by_name,
                     POLICY_PRIORITY_HIGHEST)
from .repair import repair_wheel
from .tools import EnvironmentDefault
from .wheel_abi import analyze_wheel_abi, NonPlatformWheel

logger = logging.getLogger(__name__)


def configure_parser(sub_parsers):
    policy_names = [p['name'] for p in load_policies()]
    highest_policy = get_policy_name(POLICY_PRIORITY_HIGHEST)
    help = "Vendor in external shared library dependencies of a wheel."
    p = sub_parsers.add_parser('repair', help=help, description=help)
    p.add_argument('WHEEL_FILE', help='Path to wheel file.')
    p.add_argument(
        '--plat',
        action=EnvironmentDefault,
        env='AUDITWHEEL_PLAT',
        dest='PLAT',
        help='Desired target platform. (default: "%s")' % highest_policy,
        choices=policy_names,
        default=highest_policy)
    p.add_argument('-L',
                   '--lib-sdir',
                   dest='LIB_SDIR',
                   help=('Subdirectory in packages to store copied libraries.'
                         ' (default: ".libs")'),
                   default='.libs')
    p.add_argument('-w',
                   '--wheel-dir',
                   dest='WHEEL_DIR',
                   type=abspath,
                   help=('Directory to store delocated wheels (default:'
                         ' "wheelhouse/")'),
                   default='wheelhouse/')
    p.add_argument('--no-update-tags',
                   dest='UPDATE_TAGS',
                   action='store_false',
                   help=('Do not update the wheel filename tags and WHEEL info'
                         ' to match the repaired platform tag.'),
                   default=True)
    p.add_argument('--strip',
                   dest='STRIP',
                   action='store_true',
                   help='Strip symbols in the resulting wheel',
                   default=False)
    p.set_defaults(func=execute)


def _repair_wheel(requested_tag, args, patcher):
    analyzed_tag = analyze_wheel_abi(args.WHEEL_FILE).overall_tag
    if requested_tag < get_priority_by_name(analyzed_tag):
        logger.info(('Wheel is eligible for a higher priority tag. '
                     'You requested %s but I have found this wheel is '
                     'eligible for %s.'),
                    args.PLAT, analyzed_tag)
    requested_tag = analyzed_tag
    out_wheel = repair_wheel(args.WHEEL_FILE,
                             abi=requested_tag,
                             lib_sdir=args.LIB_SDIR,
                             out_dir=args.WHEEL_DIR,
                             update_tags=args.UPDATE_TAGS,
                             patcher=patcher,
                             strip=args.STRIP)

    if out_wheel is not None:
        logger.info('\nFixed-up wheel written to %s', out_wheel)


def execute(args, p):

    if not isfile(args.WHEEL_FILE):
        p.error('cannot access %s. No such file' % args.WHEEL_FILE)

    logger.info('Repairing %s', basename(args.WHEEL_FILE))

    if not exists(args.WHEEL_DIR):
        os.makedirs(args.WHEEL_DIR)

    try:
        wheel_abi = analyze_wheel_abi(args.WHEEL_FILE)
    except NonPlatformWheel:
        logger.info('This does not look like a platform wheel')
        return 1

    reqd_tag = get_priority_by_name(args.PLAT)

    if reqd_tag > get_priority_by_name(wheel_abi.sym_tag):
        msg = ('cannot repair "%s" to "%s" ABI because of the presence '
               'of too-recent versioned symbols. You\'ll need to compile '
               'the wheel on an older toolchain.' %
               (args.WHEEL_FILE, args.PLAT))
        p.error(msg)

    if reqd_tag > get_priority_by_name(wheel_abi.ucs_tag):
        msg = ('cannot repair "%s" to "%s" ABI because it was compiled '
               'against a UCS2 build of Python. You\'ll need to compile '
               'the wheel against a wide-unicode build of Python.' %
               (args.WHEEL_FILE, args.PLAT))
        p.error(msg)

    patcher = Patchelf()
    _repair_wheel(reqd_tag, args, patcher)
