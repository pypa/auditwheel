"""The runtime dynamic linker that loads your Python extension module when it's imported doesn't have the same concept of namespaces that exists in Python, so it's possibe for symbols defined in one module to automatically, at runtime override symbols defined or used in another file, in ways that the author of that module probably didn't intend.

(This why tricks line LD_PRELOAD work.)

It's therefore good practice to limit the number of dynmic symbols that your module adds to the global symbol namespace.

This tool will print all of the (unnecessary) symbols that a wheel exports. We recommend that you try to keep this list as short as possible.

For more information on how to control visibility during compilation, see https://gcc.gnu.org/wiki/Visibility. We recommend compiling with -fvisibility=hidden and explicitly labeling only functions you want to export with ``__attribute__ ((visibility ("default")))``.

For more information on the meaning of STV_DEFAULT, STB_GLOBAL, and the like,
see http://www.sco.com/developers/gabi/2000-07-17/ch4.symtab.html.
"""
import argparse
import textwrap


def configure_subparser(sub_parsers):
    help = "List symbols exported by shared libraries in this wheel."
    description = '\n\n'.join('\n'.join(textwrap.wrap(p))
                              for p in __doc__.split('\n\n'))

    p = sub_parsers.add_parser(
        'symbols',
        help=help,
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('WHEEL_FILE', help='Path to wheel file.')
    p.add_argument(
        '-w',
        '--whitelist',
        dest='WHITELIST_FILE',
        help=
        'Skip any symbol names that appear in this file (plaintext, one per line).')
    p.set_defaults(func=execute)


def execute(args, p):
    from .symbolcheck import iter_wheel_exposed_symbols

    if args.WHITELIST_FILE is not None:
        with open(args.WHITELIST_FILE) as f:
            whitelist = {line.strip() for line in f}
            filterfunc = lambda sym: sym not in whitelist
    else:
        filterfunc = lambda x: True

    symbols = sorted(filter(filterfunc, iter_wheel_exposed_symbols(
        args.WHEEL_FILE)))

    header = [['File', 'Symbol Name', 'Visibility', 'Binding'],
              ['----', '-----------', '----------', '-------']]

    for row in format_table(header + symbols):
        print(row)
    print('\n%d symbols' % len(symbols))


def format_table(rows):
    # Reorganize data by columns
    cols = zip(*rows)
    # Compute column widths by taking maximum length of values per column
    col_widths = [2 + max(len(value) for value in col) for col in cols]
    # Create a suitable format string
    fmt = ' '.join(['%%-%ds' % width for width in col_widths])
    for row in rows:
        yield fmt % tuple(row)
