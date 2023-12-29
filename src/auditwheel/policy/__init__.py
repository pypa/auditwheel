from __future__ import annotations

import json
import logging
import platform as _platform_module
import re
import struct
import sys
from collections import defaultdict
from os.path import abspath, dirname, join
from pathlib import Path
from typing import Any, Generator

from auditwheel.elfutils import filter_undefined_symbols, is_subdir

from ..libc import Libc, get_libc
from ..musllinux import find_musl_libc, get_musl_version

_HERE = Path(__file__).parent
LIBPYTHON_RE = re.compile(r"^libpython\d+\.\d+m?.so(.\d)*$")
_MUSL_POLICY_RE = re.compile(r"^musllinux_\d+_\d+$")

logger = logging.getLogger(__name__)

_POLICY_JSON_MAP = {
    Libc.GLIBC: _HERE / "manylinux-policy.json",
    Libc.MUSL: _HERE / "musllinux-policy.json",
}


class WheelPolicies:
    def __init__(
        self,
        *,
        libc: Libc | None = None,
        musl_policy: str | None = None,
        arch: str | None = None,
    ) -> None:
        if libc is None:
            libc = get_libc() if musl_policy is None else Libc.MUSL
        if libc != Libc.MUSL and musl_policy is not None:
            raise ValueError(f"'musl_policy' shall be None for libc {libc.name}")
        if libc == Libc.MUSL:
            if musl_policy is None:
                musl_version = get_musl_version(find_musl_libc())
                musl_policy = f"musllinux_{musl_version.major}_{musl_version.minor}"
            elif _MUSL_POLICY_RE.match(musl_policy) is None:
                raise ValueError(f"Invalid 'musl_policy': '{musl_policy}'")
        if arch is None:
            arch = get_arch_name()
        policies = json.loads(_POLICY_JSON_MAP[libc].read_text())
        self._policies = []
        self._arch_name = arch
        self._libc_variant = libc
        self._musl_policy = musl_policy

        _validate_pep600_compliance(policies)
        for policy in policies:
            if self._musl_policy is not None and policy["name"] not in {
                "linux",
                self._musl_policy,
            }:
                continue
            if (
                self._arch_name in policy["symbol_versions"].keys()
                or policy["name"] == "linux"
            ):
                if policy["name"] != "linux":
                    policy["symbol_versions"] = policy["symbol_versions"][
                        self._arch_name
                    ]
                policy["name"] = policy["name"] + "_" + self._arch_name
                policy["aliases"] = [
                    alias + "_" + self._arch_name for alias in policy["aliases"]
                ]
                policy["lib_whitelist"] = _fixup_musl_libc_soname(
                    libc, arch, policy["lib_whitelist"]
                )
                self._policies.append(policy)

        if self._libc_variant == Libc.MUSL:
            assert len(self._policies) == 2, self._policies

    @property
    def policies(self):
        return self._policies

    @property
    def priority_highest(self):
        return max(p["priority"] for p in self._policies)

    @property
    def priority_lowest(self):
        return min(p["priority"] for p in self._policies)

    def get_policy_by_name(self, name: str) -> dict | None:
        matches = [
            p for p in self._policies if p["name"] == name or name in p["aliases"]
        ]
        if len(matches) == 0:
            return None
        if len(matches) > 1:
            raise RuntimeError("Internal error. Policies should be unique")
        return matches[0]

    def get_policy_name(self, priority: int) -> str | None:
        matches = [p["name"] for p in self._policies if p["priority"] == priority]
        if len(matches) == 0:
            return None
        if len(matches) > 1:
            raise RuntimeError("Internal error. priorities should be unique")
        return matches[0]

    def get_priority_by_name(self, name: str) -> int | None:
        policy = self.get_policy_by_name(name)
        return None if policy is None else policy["priority"]

    def versioned_symbols_policy(self, versioned_symbols: dict[str, set[str]]) -> int:
        def policy_is_satisfied(
            policy_name: str, policy_sym_vers: dict[str, set[str]]
        ) -> bool:
            policy_satisfied = True
            for name in set(required_vers) & set(policy_sym_vers):
                if not required_vers[name].issubset(policy_sym_vers[name]):
                    for symbol in required_vers[name] - policy_sym_vers[name]:
                        logger.debug(
                            "Package requires %s, incompatible with "
                            "policy %s which requires %s",
                            symbol,
                            policy_name,
                            policy_sym_vers[name],
                        )
                    policy_satisfied = False
            return policy_satisfied

        required_vers: dict[str, set[str]] = {}
        for symbols in versioned_symbols.values():
            for symbol in symbols:
                sym_name, _, _ = symbol.partition("_")
                required_vers.setdefault(sym_name, set()).add(symbol)
        matching_policies: list[int] = []
        for p in self.policies:
            policy_sym_vers = {
                sym_name: {sym_name + "_" + version for version in versions}
                for sym_name, versions in p["symbol_versions"].items()
            }
            if policy_is_satisfied(p["name"], policy_sym_vers):
                matching_policies.append(p["priority"])

        if len(matching_policies) == 0:
            # the base policy (generic linux) should always match
            raise RuntimeError("Internal error")

        return max(matching_policies)

    def lddtree_external_references(self, lddtree: dict, wheel_path: str) -> dict:
        # XXX: Document the lddtree structure, or put it in something
        # more stable than a big nested dict
        def filter_libs(
            libs: set[str], whitelist: set[str]
        ) -> Generator[str, None, None]:
            for lib in libs:
                if "ld-linux" in lib or lib in ["ld64.so.2", "ld64.so.1"]:
                    # always exclude ELF dynamic linker/loader
                    # 'ld64.so.2' on s390x
                    # 'ld64.so.1' on ppc64le
                    # 'ld-linux*' on other platforms
                    continue
                if LIBPYTHON_RE.match(lib):
                    # always exclude libpythonXY
                    continue
                if lib in whitelist:
                    # exclude any libs in the whitelist
                    continue
                yield lib

        def get_req_external(libs: set[str], whitelist: set[str]) -> set[str]:
            # get all the required external libraries
            libs = libs.copy()
            reqs = set()
            while libs:
                lib = libs.pop()
                reqs.add(lib)
                for dep in filter_libs(lddtree["libs"][lib]["needed"], whitelist):
                    if dep not in reqs:
                        libs.add(dep)
            return reqs

        ret: dict[str, dict[str, Any]] = {}
        for p in self.policies:
            needed_external_libs: set[str] = set()
            blacklist = {}

            if not (p["name"] == "linux" and p["priority"] == 0):
                # special-case the generic linux platform here, because it
                # doesn't have a whitelist. or, you could say its
                # whitelist is the complete set of all libraries. so nothing
                # is considered "external" that needs to be copied in.
                whitelist = set(p["lib_whitelist"])
                blacklist_libs = set(p["blacklist"].keys()) & set(lddtree["needed"])
                blacklist = {k: p["blacklist"][k] for k in blacklist_libs}
                blacklist = filter_undefined_symbols(lddtree["realpath"], blacklist)
                needed_external_libs = get_req_external(
                    set(filter_libs(lddtree["needed"], whitelist)), whitelist
                )

            pol_ext_deps = {}
            for lib in needed_external_libs:
                if is_subdir(lddtree["libs"][lib]["realpath"], wheel_path):
                    # we didn't filter libs that resolved via RPATH out
                    # earlier because we wanted to make sure to pick up
                    # our elf's indirect dependencies. But now we want to
                    # filter these ones out, since they're not "external".
                    logger.debug("RPATH FTW: %s", lib)
                    continue
                pol_ext_deps[lib] = lddtree["libs"][lib]["realpath"]
            ret[p["name"]] = {
                "libs": pol_ext_deps,
                "priority": p["priority"],
                "blacklist": blacklist,
            }
        return ret


def get_arch_name(*, bits: int | None = None) -> str:
    machine = _platform_module.machine()
    if sys.platform == "darwin" and machine == "arm64":
        return "aarch64"

    if bits is None:
        # c.f. https://github.com/pypa/packaging/pull/711
        bits = 8 * struct.calcsize("P")

    if machine in {"x86_64", "i686"}:
        return {64: "x86_64", 32: "i686"}[bits]
    if machine in {"aarch64", "armv8l"}:
        # use armv7l policy for 64-bit arm kernel in 32-bit mode (armv8l)
        return {64: "aarch64", 32: "armv7l"}[bits]
    return machine


def _validate_pep600_compliance(policies) -> None:
    symbol_versions: dict[str, dict[str, set[str]]] = {}
    lib_whitelist: set[str] = set()
    for policy in sorted(policies, key=lambda x: x["priority"], reverse=True):
        if policy["name"] == "linux":
            continue
        if not lib_whitelist.issubset(set(policy["lib_whitelist"])):
            diff = lib_whitelist - set(policy["lib_whitelist"])
            raise ValueError(
                'Invalid "policy.json" file. Missing whitelist libraries in '
                f'"{policy["name"]}" compared to previous policies: {diff}'
            )
        lib_whitelist.update(policy["lib_whitelist"])
        for arch in policy["symbol_versions"].keys():
            symbol_versions_arch = symbol_versions.get(arch, defaultdict(set))
            for prefix in policy["symbol_versions"][arch].keys():
                policy_symbol_versions = set(policy["symbol_versions"][arch][prefix])
                if not symbol_versions_arch[prefix].issubset(policy_symbol_versions):
                    diff = symbol_versions_arch[prefix] - policy_symbol_versions
                    raise ValueError(
                        'Invalid "policy.json" file. Symbol versions missing '
                        f'in "{policy["name"]}_{arch}" for "{prefix}" '
                        f"compared to previous policies: {diff}"
                    )
                symbol_versions_arch[prefix].update(
                    policy["symbol_versions"][arch][prefix]
                )
            symbol_versions[arch] = symbol_versions_arch


def _fixup_musl_libc_soname(libc: Libc, arch: str, whitelist):
    if libc != Libc.MUSL:
        return whitelist
    soname_map = {
        "libc.so": {
            "x86_64": "libc.musl-x86_64.so.1",
            "i686": "libc.musl-x86.so.1",
            "aarch64": "libc.musl-aarch64.so.1",
            "s390x": "libc.musl-s390x.so.1",
            "ppc64le": "libc.musl-ppc64le.so.1",
            "armv7l": "libc.musl-armv7.so.1",
        }
    }
    new_whitelist = []
    for soname in whitelist:
        if soname in soname_map:
            new_soname = soname_map[soname][arch]
            logger.debug(f"Replacing whitelisted '{soname}' by '{new_soname}'")
            new_whitelist.append(new_soname)
        else:
            new_whitelist.append(soname)
    return new_whitelist


def get_replace_platforms(name: str) -> list[str]:
    """Extract platform tag replacement rules from policy

    >>> get_replace_platforms('linux_x86_64')
    []
    >>> get_replace_platforms('linux_i686')
    []
    >>> get_replace_platforms('manylinux1_x86_64')
    ['linux_x86_64']
    >>> get_replace_platforms('manylinux1_i686')
    ['linux_i686']

    """
    if name.startswith("linux"):
        return []
    if name.startswith("manylinux_"):
        return ["linux_" + "_".join(name.split("_")[3:])]
    if name.startswith("musllinux_"):
        return ["linux_" + "_".join(name.split("_")[3:])]
    return ["linux_" + "_".join(name.split("_")[1:])]


def _load_policy_schema():
    with open(join(dirname(abspath(__file__)), "policy-schema.json")) as f_:
        schema = json.load(f_)
    return schema


__all__ = [
    "WheelPolicies",
]
