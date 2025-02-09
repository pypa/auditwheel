from __future__ import annotations

import functools
import itertools
import logging
import os
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from os.path import basename
from typing import Any

from . import json
from .architecture import Architecture
from .elfutils import (
    elf_file_filter,
    elf_find_ucs2_symbols,
    elf_find_versioned_symbols,
    elf_is_python_extension,
    elf_references_PyFPE_jbuf,
)
from .genericpkgctx import InGenericPkgCtx
from .lddtree import DynamicExecutable, ldd
from .policy import WheelPolicies

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WheelAbIInfo:
    overall_tag: str
    external_refs: dict[str, Any]
    ref_tag: str
    versioned_symbols: dict[str, set[str]]
    sym_tag: str
    ucs_tag: str
    pyfpe_tag: str
    blacklist_tag: str
    machine_tag: str


class WheelAbiError(Exception):
    """Root exception class"""


class NonPlatformWheel(WheelAbiError):
    """No ELF binaries in the wheel"""

    def __init__(self, architecture: Architecture, libraries: list[str]) -> None:
        if not libraries:
            msg = (
                "This does not look like a platform wheel, no ELF executable "
                "or shared library file (including compiled Python C extension) "
                "found in the wheel archive"
            )
        else:
            libraries_str = "\n\t".join(libraries)
            msg = (
                "Invalid binary wheel: no ELF executable or shared library file "
                "(including compiled Python C extension) with a "
                f"{architecture.value!r} architecure found. The following "
                f"ELF files were found:\n\t{libraries_str}\n"
            )
        super().__init__(msg)

    @property
    def message(self) -> str:
        assert isinstance(self.args[0], str)
        return self.args[0]


@functools.lru_cache
def get_wheel_elfdata(  # type: ignore[no-untyped-def]
    wheel_policy: WheelPolicies, wheel_fn: str, exclude: frozenset[str]
):
    full_elftree = {}
    nonpy_elftree = {}
    full_external_refs = {}
    versioned_symbols: dict[str, set[str]] = defaultdict(set)
    uses_ucs2_symbols = False
    uses_PyFPE_jbuf = False

    with InGenericPkgCtx(wheel_fn) as ctx:
        shared_libraries_in_purelib = []
        shared_libraries_with_invalid_machine = []

        platform_wheel = False
        for fn, elf in elf_file_filter(ctx.iter_files()):
            # Check for invalid binary wheel format: no shared library should
            # be found in purelib
            so_path_split = fn.split(os.sep)
            so_name = so_path_split[-1]

            # If this is in purelib, add it to the list of shared libraries in
            # purelib
            if "purelib" in so_path_split:
                shared_libraries_in_purelib.append(so_name)

            # If at least one shared library exists in purelib, this is going
            # to fail and there's no need to do further checks
            if not shared_libraries_in_purelib:
                log.debug("processing: %s", fn)
                elftree = ldd(fn, exclude=exclude)

                try:
                    arch = elftree.platform.baseline_architecture
                    if arch != wheel_policy.architecture.baseline:
                        shared_libraries_with_invalid_machine.append(so_name)
                        log.warning("ignoring: %s with %s architecture", so_name, arch)
                        continue
                except ValueError:
                    shared_libraries_with_invalid_machine.append(so_name)
                    log.warning("ignoring: %s with unknown architecture", so_name)
                    continue

                platform_wheel = True

                for key, value in elf_find_versioned_symbols(elf):
                    log.debug("key %s, value %s", key, value)
                    versioned_symbols[key].add(value)

                is_py_ext, py_ver = elf_is_python_extension(fn, elf)

                # If the ELF is a Python extention, we definitely need to
                # include its external dependencies.
                if is_py_ext:
                    full_elftree[fn] = elftree
                    uses_PyFPE_jbuf |= elf_references_PyFPE_jbuf(elf)
                    if py_ver == 2:
                        uses_ucs2_symbols |= any(
                            True for _ in elf_find_ucs2_symbols(elf)
                        )
                    full_external_refs[fn] = wheel_policy.lddtree_external_references(
                        elftree, ctx.path
                    )
                else:
                    # If the ELF is not a Python extension, it might be
                    # included in the wheel already because auditwheel repair
                    # vendored it, so we will check whether we should include
                    # its internal references later.
                    nonpy_elftree[fn] = elftree

        # If at least one shared library exists in purelib, raise an error
        if shared_libraries_in_purelib:
            libraries = "\n\t".join(shared_libraries_in_purelib)
            msg = (
                "Invalid binary wheel, found the following shared library/libraries "
                f"in purelib folder:\n\t{libraries}\n"
                "The wheel has to be platlib compliant in order to be repaired by "
                "auditwheel."
            )
            raise RuntimeError(msg)

        if not platform_wheel:
            raise NonPlatformWheel(
                wheel_policy.architecture, shared_libraries_with_invalid_machine
            )

        # Get a list of all external libraries needed by ELFs in the wheel.
        needed_libs = {
            lib
            for elf in itertools.chain(full_elftree.values(), nonpy_elftree.values())
            for lib in elf.needed
        }

        for fn, elf_tree in nonpy_elftree.items():
            # If a non-pyextension ELF file is not needed by something else
            # inside the wheel, then it was not checked by the logic above and
            # we should walk its elftree.
            if basename(fn) not in needed_libs:
                full_elftree[fn] = elf_tree

            # Even if a non-pyextension ELF file is not needed, we
            # should include it as an external reference, because
            # it might require additional external libraries.
            full_external_refs[fn] = wheel_policy.lddtree_external_references(
                elf_tree, ctx.path
            )

    log.debug("full_elftree:\n%s", json.dumps(full_elftree))
    log.debug(
        "full_external_refs (will be repaired):\n%s", json.dumps(full_external_refs)
    )

    return (
        full_elftree,
        full_external_refs,
        versioned_symbols,
        uses_ucs2_symbols,
        uses_PyFPE_jbuf,
    )


def get_external_libs(external_refs: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Get external library dependencies for all policies excluding the default
    linux policy
    :param external_refs: external references for all policies
    :return: {realpath: soname} e.g.
    {'/path/to/external_ref.so.1.2.3': 'external_ref.so.1'}
    """
    result: dict[str, str] = {}
    for policy in external_refs.values():
        # linux tag (priority 0) has no white-list, do not analyze it
        if policy["priority"] == 0:
            continue
        # go through all libs, retrieving their soname and realpath
        for libname, realpath in policy["libs"].items():
            if realpath and realpath not in result:
                result[realpath] = libname
    return result


def get_versioned_symbols(libs: dict[str, str]) -> dict[str, dict[str, set[str]]]:
    """Get versioned symbols used in libraries
    :param libs: {realpath: soname} dict to search for versioned symbols e.g.
    {'/path/to/external_ref.so.1.2.3': 'external_ref.so.1'}
    :return: {soname: {depname: set([symbol_version])}} e.g.
    {'external_ref.so.1': {'libc.so.6', set(['GLIBC_2.5','GLIBC_2.12'])}}
    """
    result = {}
    for path, elf in elf_file_filter(libs.keys()):
        # {depname: set(symbol_version)}, e.g.
        # {'libc.so.6', set(['GLIBC_2.5','GLIBC_2.12'])}
        elf_versioned_symbols: dict[str, set[str]] = defaultdict(set)
        for key, value in elf_find_versioned_symbols(elf):
            log.debug("path %s, key %s, value %s", path, key, value)
            elf_versioned_symbols[key].add(value)
        result[libs[path]] = elf_versioned_symbols
    return result


def get_symbol_policies(
    wheel_policy: WheelPolicies,
    versioned_symbols: dict[str, set[str]],
    external_versioned_symbols: dict[str, dict[str, set[str]]],
    external_refs: dict[str, dict[str, Any]],
) -> list[tuple[int, dict[str, set[str]]]]:
    """Get symbol policies
    Since white-list is different per policy, this function inspects
    versioned_symbol per policy when including external refs
    :param versioned_symbols: versioned symbols for the current wheel
    :param external_versioned_symbols: versioned symbols for external libs
    :param external_refs: external references for all policies
    :return: list of tuples of the form (policy_priority, versioned_symbols),
    e.g. [(100, {'libc.so.6', set(['GLIBC_2.5'])})]
    """
    result = []
    for policy in external_refs.values():
        # skip the linux policy
        if policy["priority"] == 0:
            continue
        policy_symbols = deepcopy(versioned_symbols)
        for soname in policy["libs"]:
            if soname not in external_versioned_symbols:
                continue
            ext_symbols = external_versioned_symbols[soname]
            for k in iter(ext_symbols):
                policy_symbols[k].update(ext_symbols[k])
        result.append(
            (wheel_policy.versioned_symbols_policy(policy_symbols), policy_symbols)
        )
    return result


def _get_machine_policy(
    wheel_policy: WheelPolicies,
    elftree_by_fn: dict[str, DynamicExecutable],
    external_so_names: frozenset[str],
) -> int:
    result = wheel_policy.priority_highest
    machine_to_check = {}
    for fn, dynamic_executable in elftree_by_fn.items():
        if fn in machine_to_check:
            continue
        machine_to_check[fn] = dynamic_executable.platform.extended_architecture
        for dependency in dynamic_executable.libraries.values():
            if dependency.soname not in external_so_names:
                continue
            if dependency.realpath is None:
                continue
            assert dependency.platform is not None
            if dependency.realpath in machine_to_check:
                continue
            machine_to_check[dependency.realpath] = (
                dependency.platform.extended_architecture
            )

    for fn, extended_architecture in machine_to_check.items():
        if extended_architecture is None:
            continue
        if wheel_policy.architecture.is_superset(extended_architecture):
            continue
        log.warning(
            "ELF file %r requires %r instruction set, not in %r",
            fn,
            extended_architecture.value,
            wheel_policy.architecture.value,
        )
        result = wheel_policy.priority_lowest

    return result


def analyze_wheel_abi(
    wheel_policy: WheelPolicies,
    wheel_fn: str,
    exclude: frozenset[str],
    disable_isa_ext_check: bool,
) -> WheelAbIInfo:
    external_refs = {
        p["name"]: {"libs": {}, "blacklist": {}, "priority": p["priority"]}
        for p in wheel_policy.policies
    }

    (
        elftree_by_fn,
        external_refs_by_fn,
        versioned_symbols,
        has_ucs2,
        uses_PyFPE_jbuf,
    ) = get_wheel_elfdata(wheel_policy, wheel_fn, exclude)

    for fn in elftree_by_fn:
        update(external_refs, external_refs_by_fn[fn])

    log.debug("external reference info")
    log.debug(json.dumps(external_refs))

    external_libs = get_external_libs(external_refs)
    external_versioned_symbols = get_versioned_symbols(external_libs)
    symbol_policies = get_symbol_policies(
        wheel_policy, versioned_symbols, external_versioned_symbols, external_refs
    )
    symbol_policy = wheel_policy.versioned_symbols_policy(versioned_symbols)

    # let's keep the highest priority policy and
    # corresponding versioned_symbols
    symbol_policy, versioned_symbols = max(
        symbol_policies, key=lambda x: x[0], default=(symbol_policy, versioned_symbols)
    )

    ref_policy = max(
        (e["priority"] for e in external_refs.values() if len(e["libs"]) == 0),
        default=wheel_policy.priority_lowest,
    )

    blacklist_policy = max(
        (e["priority"] for e in external_refs.values() if len(e["blacklist"]) == 0),
        default=wheel_policy.priority_lowest,
    )

    if disable_isa_ext_check:
        machine_policy = wheel_policy.priority_highest
    else:
        machine_policy = _get_machine_policy(
            wheel_policy, elftree_by_fn, frozenset(external_libs.values())
        )

    if has_ucs2:
        ucs_policy = wheel_policy.priority_lowest
    else:
        ucs_policy = wheel_policy.priority_highest

    if uses_PyFPE_jbuf:
        pyfpe_policy = wheel_policy.priority_lowest
    else:
        pyfpe_policy = wheel_policy.priority_highest

    ref_tag = wheel_policy.get_policy_name(ref_policy)
    sym_tag = wheel_policy.get_policy_name(symbol_policy)
    ucs_tag = wheel_policy.get_policy_name(ucs_policy)
    pyfpe_tag = wheel_policy.get_policy_name(pyfpe_policy)
    blacklist_tag = wheel_policy.get_policy_name(blacklist_policy)
    machine_tag = wheel_policy.get_policy_name(machine_policy)
    overall_tag = wheel_policy.get_policy_name(
        min(
            symbol_policy,
            ref_policy,
            ucs_policy,
            pyfpe_policy,
            blacklist_policy,
            machine_policy,
        )
    )

    return WheelAbIInfo(
        overall_tag,
        external_refs,
        ref_tag,
        versioned_symbols,
        sym_tag,
        ucs_tag,
        pyfpe_tag,
        blacklist_tag,
        machine_tag,
    )


def update(d: dict[str, Any], u: Mapping[str, Any]) -> dict[str, Any]:
    for k, v in u.items():
        if k == "blacklist":
            for lib, symbols in v.items():
                if lib not in d[k]:
                    d[k][lib] = list(symbols)
                else:
                    d[k][lib] = sorted(set(d[k][lib]) | set(symbols))
        elif isinstance(v, Mapping):
            r = update(d.get(k, {}), v)
            d[k] = r
        elif isinstance(v, (str, int, float, type(None))):
            d[k] = u[k]
        else:
            msg = f"can't update {d} {k}"
            raise RuntimeError(msg)
    return d
