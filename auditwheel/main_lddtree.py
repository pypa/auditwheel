def configure_subparser(sub_parsers):
    help = 'Analyze a single ELF file (similar to ``ldd``).'
    p = sub_parsers.add_parser('lddtree', help=help, description=help)
    p.add_argument('file', help='Path to .so file')
    p.set_defaults(func=execute)


def execute(args, p):
    import json
    from .lddtree import lddtree

    print(json.dumps(lddtree(args.file), indent=4))
