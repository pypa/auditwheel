def configure_parser(sub_parsers):
    help = "Audit a wheel for external shared library dependencies."
    p = sub_parsers.add_parser('show', help=help, description=help)
    p.add_argument('WHEEL_FILE', help='Path to wheel file.')
    p.set_defaults(func=execute)


def printp(text):
    from textwrap import wrap
    print()
    print('\n'.join(wrap(text)))


def execute(args, p):
    import json
    import os
    from functools import reduce
    from collections import OrderedDict
    from os.path import isfile, basename
    from wheel.install import WheelFile
    from .policy import (load_policies, get_priority_by_name,
                         POLICY_PRIORITY_LOWEST, POLICY_PRIORITY_HIGHEST,
                         get_policy_name)
    from .wheel_abi import analyze_wheel_abi
    from .termcolor import colored
    fn = basename(args.WHEEL_FILE)

    if not isfile(args.WHEEL_FILE):
        p.error('cannot access %s. No such file' % args.WHEEL_FILE)

    winfo = analyze_wheel_abi(args.WHEEL_FILE)
    versions = ['%s_%s' % (k, v) for k, v in winfo.versioned_symbols.items()]


    # WheelAbIInfo(overall_tag='linux_x86_64', external_refs={'linux_x86_64': {'libs': {'libffi.so.5': None, 'libpthread.so.0': '/lib/x86_64-linux-gnu/libpthread-2.21.so', 'libc.so.6': '/lib/x86_64-linux-gnu/libc-2.21.so'}, 'priority': 0}, 'manylinux1_x86_64': {'libs': {'libffi.so.5': None}, 'priority': 100}}, ref_tag='linux_x86_64', versioned_symbols={'GLIBC': NormalizedVersion('2.3')}, sym_tag='manylinux1_x86_64')

    lines = ['Symbol Versioning',
             '-----------------']
    if len(versions) == 0:
        lines.extend(["The wheel references no external versioned symbols from ",
                      "system-provided shared libraries."])
    else:
        lines.extend(['The wheel references the following external versioned symbols in',
                      'system-provided shared libraries: %s.' %
                      ', '.join(versions)])
    if get_priority_by_name(winfo.sym_tag) < POLICY_PRIORITY_HIGHEST:
        lines.append(('This constrains the platform tag to "%s". '
                      'In order to achieve a more compatible tag, you '
                      'would to recompile a new wheel from source on a system '
                      'with earlier versions of these libraries, such as '
                      'CentOS 5.') % colored(winfo.sym_tag, color='red'))
    else:
        lines.append('This is %s with the manylinux1 tag.' % colored('consistent', color='green'))


    lines.extend(['', 'External Libraries', '------------------'])
    libs = winfo.external_refs[get_policy_name(POLICY_PRIORITY_LOWEST)]['libs']
    if len(libs) == 0:
        lines.extend(['The wheel requires no external shared libraries! :).',
                      'This is %s with the manylinux1 tag' % colored('consistent', color='green')])
    else:
         lines.append(('The following external shared libraries are required '
                 'by the wheel:'))
         lines.append(json.dumps(OrderedDict(sorted(libs.items())), indent=4))
         lines.append('This is %s with the manylinux1 tag.' % colored('inconsistent', color='red')) 

    for p in sorted(load_policies(), key=lambda p: p['priority']):
        if p['priority'] > get_priority_by_name(winfo.overall_tag):
            lines.extend(['In order to achieve the tag platform tag "%s" the following' % p['name'],
                          'shared library dependencies will need to be eliminated:'])
            lines.append(', '.join(sorted(winfo.external_refs[p['name']]['libs'].keys())))


    lines.extend(['', 'Unicode', '-------'])

    wheel = WheelFile(args.WHEEL_FILE)
    if any(pyver.startswith('cp2') or pyver in ('cp30', 'cp31', 'cp32') and abi is 'none' for (pyver, abi, plat) in wheel.tags):
        lines.extend(['This wheel has a "none" ABI tag. Rebuild with the latest',
                      'release of ``pip install wheel`` to fix. This is %s' % colored('inconsistent', color='red'),
                      'with the manylinux1 tag.'])
    else:
        lines.extend(['The unicode ABI is properly declared.',
                      'This is %s with the manylinux1 tag' % colored('consistent', color='green')])

    print(os.linesep.join(lines))
