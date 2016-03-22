from os.path import basename, exists, join, abspath
from .policy import (load_policies, get_policy_name, get_priority_by_name,
                     POLICY_PRIORITY_HIGHEST)


def configure_parser(sub_parsers):
    help = "Add new platform ABI tags to a wheel"

    p = sub_parsers.add_parser('addtag', help=help, description=help)
    p.add_argument('WHEEL_FILE', help='Path to wheel file')
    p.add_argument('-w',
                   '--wheel-dir',
                   dest='WHEEL_DIR',
                   help=('Directory to store new wheel file (default:'
                         ' "wheelhouse/")'),
                   type=abspath,
                   default='wheelhouse/')
    p.set_defaults(func=execute)


def execute(args, p):
    import os
    import sys
    from wheel.install import WHEEL_INFO_RE  # type: ignore
    from .wheeltools import InWheelCtx, add_platforms, WheelToolsError
    from .wheel_abi import analyze_wheel_abi

    wheel_abi = analyze_wheel_abi(args.WHEEL_FILE)

    parsed_fname = WHEEL_INFO_RE(basename(args.WHEEL_FILE))
    in_fname_tags = parsed_fname.groupdict()['plat'].split('.')

    print('%s recieves the following tag: "%s".' % (basename(args.WHEEL_FILE),
                                                    wheel_abi.overall_tag))
    print('Use ``auditwheel show`` for more details')

    if wheel_abi.overall_tag in in_fname_tags:
        print('No tags to be added. Exiting.')
        return 1

    # todo: move more of this logic to separate file
    if not exists(args.WHEEL_DIR):
        os.makedirs(args.WHEEL_DIR)

    with InWheelCtx(args.WHEEL_FILE) as ctx:
        try:
            out_wheel = add_platforms(ctx, [wheel_abi.overall_tag])
        except WheelToolsError as e:
            print('\n%s.' % str(e), file=sys.stderr)
            return 1

        if out_wheel:
            # tell context manager to write wheel on exit with
            # the proper output directory
            ctx.out_wheel = join(args.WHEEL_DIR, basename(out_wheel))
            print('\nUpdated wheel written to %s' % out_wheel)
    return 0
