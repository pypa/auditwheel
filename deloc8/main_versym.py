import os
import json

from .wheel_abi import analyze_wheel_abi


def configure_parser(sub_parsers):
    help = "List versioned symbols in a wheel"
    p = sub_parsers.add_parser('versym', help=help, description=help)
    p.add_argument('wheel', help='Path to wheel file')
    p.set_defaults(func=execute)


def execute(args, p):
    if not os.path.isfile(args.wheel):
        p.error('cannot access %s. No such file' % args.wheel)

    tag, _, _, versioned_syms, sym_tag = analyze_wheel_abi(args.wheel)

    print('\n%s references the following versioned external symbols: ' %
          os.path.basename(args.wheel))
    print(json.dumps(versioned_syms, indent=4))

    if tag == sym_tag:
        print('Based on this information, %s is assigned the following '
              'ABI tag: "%s"' % (os.path.basename(args.wheel), tag))
    else:
        print('Based on this information alone, %s would be assigned the '
              'following ABI tag: "%s". However, other factors such as '
              'external shared library dependencies constrain the ABI '
              'tag to: "%s".' % (os.path.basename(args.wheel), sym_tag, tag))
