def configure_parser(sub_parsers):
    help = "List external shared library dependencies of a wheel."
    p = sub_parsers.add_parser('listdeps', help=help, description=help)
    p.add_argument('wheel', help='Path to wheel file.')
    p.set_defaults(func=execute)


def execute(args, p):
    import json
    from os.path import isfile, basename
    from .policy import load_policies, get_priority_by_name
    from .wheel_abi import analyze_wheel_abi

    if not isfile(args.wheel):
        p.error('cannot access %s. No such file' % args.wheel)

    tag, external_refs, ref_tag, _, _ = analyze_wheel_abi(args.wheel)

    if tag == ref_tag:
        print('Based on external shared library dependencies, "%s" is '
              'assigned the following ABI tag: "%s".' % (basename(args.wheel),
                                                         tag))

        for p in sorted(load_policies(), key=lambda p: p['priority']):
            if p['priority'] > get_priority_by_name(tag):
                print('\nTo acheive the the "%s" ABI tag, the following '
                      'external shared\nlibrary dependencies would need to '
                      'be relocated inside the wheel:' % p['name'])
                print(json.dumps(external_refs[p['name']]['libs'],
                                 indent=4))
    else:
        print('Based on external shared library dependencies, "%s" would '
              'be assigned the following ABI tag: "%s". However, other '
              'factors such as versioned symbols constrain the ABI tag '
              'to: "%s".' % (basename(args.wheel), ref_tag, tag))
