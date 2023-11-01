from __future__ import annotations

import json
import logging
import platform as _platform_module
import sys
from collections import defaultdict
from os.path import abspath, dirname, join
from pathlib import Path

from ..libc import Libc, get_libc
from ..musllinux import find_musl_libc, get_musl_version

_HERE = Path(__file__).parent

logger = logging.getLogger(__name__)

# https://docs.python.org/3/library/platform.html#platform.architecture
bits = 8 * (8 if sys.maxsize > 2**32 else 4)

_POLICY_JSON_MAP = {
    Libc.GLIBC: _HERE / "manylinux-policy.json",
    Libc.MUSL: _HERE / "musllinux-policy.json",
}


class WheelPolicies:
    def __init__(self) -> None:
        libc_variant = get_libc()
        policies_path = _POLICY_JSON_MAP[libc_variant]
        policies = json.loads(policies_path.read_text())
        self._policies = []
        self._musl_policy = _get_musl_policy()
        self._arch_name = get_arch_name()
        self._libc_variant = get_libc()

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
                    policy["lib_whitelist"]
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


def get_arch_name() -> str:
    machine = _platform_module.machine()
    if sys.platform == "darwin" and machine == "arm64":
        return "aarch64"
    if machine in {"x86_64", "i686"}:
        return {64: "x86_64", 32: "i686"}[bits]
    if machine in {"aarch64", "armv8l"}:
        # use armv7l policy for 64-bit arm kernel in 32-bit mode (armv8l)
        return {64: "aarch64", 32: "armv7l"}[bits]
    return machine


_ARCH_NAME = get_arch_name()
_LIBC = get_libc()


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


def _get_musl_policy():
    if _LIBC != Libc.MUSL:
        return None
    musl_version = get_musl_version(find_musl_libc())
    return f"musllinux_{musl_version.major}_{musl_version.minor}"


def _fixup_musl_libc_soname(whitelist):
    if _LIBC != Libc.MUSL:
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
            new_soname = soname_map[soname][_ARCH_NAME]
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


# These have to be imported here to avoid a circular import.
from .external_references import lddtree_external_references  # noqa
from .versioned_symbols import versioned_symbols_policy  # noqa

def _load_policy_schema():
    with open(join(dirname(abspath(__file__)), "policy-schema.json")) as f_:
        schema = json.load(f_)
    return schema


__all__ = [
    "lddtree_external_references",
    "versioned_symbols_policy",
    "WheelPolicies",
]
