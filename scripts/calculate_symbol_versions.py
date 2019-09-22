"""
Calculate symbol_versions for a policy in policy.json by collection
defined version (.gnu.version_d) from libraries in lib_whitelist.
This should be run inside a manylinux Docker container.
"""
import argparse
import os
import platform
import json
from elftools.elf.elffile import ELFFile

if platform.architecture()[0] == '64bit':
    LIBRARY_PATHS = ['/lib64', '/usr/lib64']
else:
    LIBRARY_PATHS = ['/lib', '/usr/lib']

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("policy", help="The policy name")
parser.add_argument("policyjson", help="The policy.json file.")


def load_policies(path):
    with open(path) as f:
        return json.load(f)


def choose_policy(name, policies):
    try:
        return next(policy for policy in policies if policy['name'] == name)
    except StopIteration:
        raise RuntimeError("Unknown policy {}".format(name))


def find_library(library):
    for p in LIBRARY_PATHS:
        path = os.path.join(p, library)
        if os.path.exists(path):
            return path
    else:
        raise RuntimeError("Unknown library {}".format(library))


def versionify(version_string):
    try:
        result = [int(n) for n in version_string.split('.')]
        assert len(result) <= 3
    except ValueError:
        result = [999999, 999999, 999999, version_string]
    return result


def calculate_symbol_versions(libraries, symbol_versions, arch):
    calculated_symbol_versions = {k: set() for k in symbol_versions}
    prefixes = ['/lib', '/usr/lib']
    if arch == '64bit':
        prefixes = [p + '64' for p in prefixes]

    for library in libraries:
        library_path = find_library(library)
        with open(library_path, 'rb') as f:
            e = ELFFile(f)
            section = e.get_section_by_name('.gnu.version_d')
            if section:
                for _, verdef_iter in section.iter_versions():
                    for vernaux in verdef_iter:
                        for symbol_name in symbol_versions:
                            try:
                                name, version = vernaux.name.split('_', 1)
                            except ValueError:
                                pass
                            if name in calculated_symbol_versions \
                               and version != 'PRIVATE':
                                calculated_symbol_versions[name].add(version)
    return {
        k: sorted(v, key=versionify)
        for k, v in calculated_symbol_versions.items()
    }


def main():
    args = parser.parse_args()
    policies = load_policies(args.policyjson)
    policy = choose_policy(args.policy, policies)
    arch, _ = platform.architecture()
    print(
        json.dumps(
            calculate_symbol_versions(
                policy['lib_whitelist'],
                policy['symbol_versions'],
                arch,
            )
        )
    )


main()
