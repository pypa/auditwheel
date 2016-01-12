import os
import json

from .wheel_abi import analyze_wheel_abi


def configure_parser(sub_parsers):
    p = sub_parsers.add_parser(
        'listdeps',
        help="List shared library dependencies of a wheel",
        description="List shared library dependencies of a wheel")
    p.add_argument('wheel', help='Path to wheel file')
    p.set_defaults(func=execute)


def execute(args, p):
    if not os.path.isfile(args.wheel):
        p.error('cannot access %s. No such file' % args.wheel)

    tag, external_refs, ref_tag, _, _ = analyze_wheel_abi(args.wheel)

    print('\n%s references the following external '
          'shared library dependencies:' % os.path.basename(args.wheel))
    print(json.dumps(
        {k: {'note': v['note'],
             'path': v['path']}
         for k, v in external_refs.items() if v['note'] is not 'whitelist'},
        indent=4))

    if tag == ref_tag:
        print('Based on this information, %s is assigned the following '
              'ABI tag: "%s".' % (os.path.basename(args.wheel), tag))
    else:
        print('Based on this information alone, %s would be assigned the '
              'following ABI tag: "%s". However, other factors such as '
              'versioned symbols constrain the ABI tag to: "%s".' % (
                  os.path.basename(args.wheel), ref_tag, tag))
