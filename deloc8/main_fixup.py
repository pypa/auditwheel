from .policy import (load_policies, get_policy_name, get_priority_by_name,
                     POLICY_PRIORITY_HIGHEST)


def configure_parser(sub_parsers):
    policy_names = [p['name'] for p in load_policies()]
    highest_policy = get_policy_name(POLICY_PRIORITY_HIGHEST)
    help = "Fix up external shared library dependencies of a wheel."

    p = sub_parsers.add_parser('fixup', help=help, description=help)
    p.add_argument('wheel', help='Path to wheel file')
    p.add_argument('-f',
                   '--force',
                   help='Override symbol version ABI check',
                   action='store_true')
    p.add_argument(
        '--abi',
        help='Desired target ABI tags. (default: "%s")' % highest_policy,
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
                   help=('Directory to store delocated wheels (default:'
                         ' "wheelhouse/")'),
                   default='wheelhouse/')
    p.set_defaults(func=execute)


def execute(args, p):
    import os
    import logging
    from os.path import isfile, exists
    from distutils.spawn import find_executable
    from .fixup import fixup_wheel
    from .wheel_abi import analyze_wheel_abi
    log = logging.getLogger(__name__)

    if not isfile(args.wheel):
        p.error('cannot access %s. No such file' % args.wheel)
    if find_executable('patchelf') is None:
        p.error('cannot find the \'patchelf\' tool, which is required')

    wheel_abi = analyze_wheel_abi(args.wheel)
    can_add_platform = (get_priority_by_name(args.abi) <=
                        get_priority_by_name(wheel_abi.sym_tag))

    if not can_add_platform:
        msg = ('cannot really fixup "%s" to "%s" ABI because of the presence '
               'of too-recent versioned symbols. You\'ll need to compile '
               'the wheel on an older toolchain. Try: ...' %
               (args.wheel, args.abi))
        if not args.force:
            p.error(msg)
        else:
            log.warn(msg)
            log.warn('you were warned...')

    if not exists(args.WHEEL_DIR):
        os.makedirs(args.WHEEL_DIR)

    out_wheel = fixup_wheel(args.wheel,
                            abi=args.abi,
                            lib_sdir=args.LIB_SDIR,
                            out_dir=args.WHEEL_DIR,
                            add_platform_tag=can_add_platform)
    if out_wheel is not None:
        print('\nWriting fixed-up wheel written to %s...' % out_wheel)
        print('Done!')
    else:
        print('\nWheel already contains requested ABI tag')
