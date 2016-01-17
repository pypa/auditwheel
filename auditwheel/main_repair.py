from .policy import (load_policies, get_policy_name, get_priority_by_name,
                     POLICY_PRIORITY_HIGHEST)


def configure_parser(sub_parsers):
    policy_names = [p['name'] for p in load_policies()]
    highest_policy = get_policy_name(POLICY_PRIORITY_HIGHEST)
    help = "Vendor in external shared library dependencies of a wheel."
    p = sub_parsers.add_parser('repair', help=help, description=help)
    p.add_argument('WHEEL_FILE', help='Path to wheel file.')
    p.add_argument('-f',
                   '--force',
                   help='Override symbol version ABI check',
                   action='store_true')
    p.add_argument(
        '--plat',
        dest='PLAT',
        help='Desired target platform. (default: "%s")' % highest_policy,
        choices=policy_names,
        default=highest_policy)
    p.add_argument(
        '-a',
        '--add-tag',
        dest='ADD_TAG',
        help=("Add new platform tag to wheel. (this doesn't work"
              "with the current pip, since it doesn't recognize the tag"),
        action="store_true")
    p.add_argument('-L',
                   '--lib-sdir',
                   dest='LIB_SDIR',
                   help=('Subdirectory in packages to store copied libraries.'
                         ' (default: ".libs")'),
                   default='.libs')
    p.add_argument('-w',
                   '--wheel-dir',
                   dest='WHEEL_DIR',
                   help=('Directory to store delocated wheels (default:'
                         ' "wheelhouse/")'),
                   default='wheelhouse/')
    p.set_defaults(func=execute)


def execute(args, p):
    import os
    import logging
    from os.path import isfile, exists
    from distutils.spawn import find_executable
    from .repair import repair_wheel
    from .wheel_abi import analyze_wheel_abi
    log = logging.getLogger(__name__)

    if not isfile(args.WHEEL_FILE):
        p.error('cannot access %s. No such file' % args.WHEEL_FILE)
    if find_executable('patchelf') is None:
        p.error('cannot find the \'patchelf\' tool, which is required')

    if not exists(args.WHEEL_DIR):
        os.makedirs(args.WHEEL_DIR)

    wheel_abi = analyze_wheel_abi(args.WHEEL_FILE)
    out_wheel = repair_wheel(args.WHEEL_FILE,
                             abi=args.PLAT,
                             lib_sdir=args.LIB_SDIR,
                             out_dir=args.WHEEL_DIR)

    if out_wheel is not None:
        print('\nWriting fixed-up wheel written to %s' % out_wheel)
