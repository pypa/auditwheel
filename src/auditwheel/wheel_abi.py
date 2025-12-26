from __future__ import annotations

import functools
import itertools
import logging
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from . import json
from .architecture import Architecture
from .elfutils import (
    elf_file_filter,
    elf_find_ucs2_symbols,
    elf_find_versioned_symbols,
    elf_is_python_extension,
    elf_references_PyFPE_jbuf,
)
from .error import InvalidLibc, NonPlatformWheel
from .genericpkgctx import InGenericPkgCtx
from .lddtree import DynamicExecutable, ldd
from .libc import Libc
from .policy import ExternalReference, Policy, WheelPolicies

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WheelAbIInfo:
    policies: WheelPolicies
    full_external_refs: dict[Path, dict[str, ExternalReference]]
    overall_policy: Policy
    external_refs: dict[str, ExternalReference]
    ref_policy: Policy
    versioned_symbols: dict[str, set[str]]
    sym_policy: Policy
    ucs_policy: Policy
    pyfpe_policy: Policy
    blacklist_policy: Policy
    machine_policy: Policy


@dataclass(frozen=True)
class WheelElfData:
    policies: WheelPolicies
    full_elftree: dict[Path, DynamicExecutable]
    full_external_refs: dict[Path, dict[str, ExternalReference]]
    versioned_symbols: dict[str, set[str]]
    uses_ucs2_symbols: bool
    uses_PyFPE_jbuf: bool


@functools.lru_cache
def get_wheel_elfdata(
    libc: Libc | None,
    architecture: Architecture | None,
    wheel_fn: Path,
    exclude: frozenset[str],
) -> WheelElfData:
    full_elftree: dict[Path, DynamicExecutable] = {}
    nonpy_elftree: dict[Path, DynamicExecutable] = {}
    full_external_refs: dict[Path, dict[str, ExternalReference]] = {}
    versioned_symbols: dict[str, set[str]] = defaultdict(set)
    uses_ucs2_symbols = False
    uses_PyFPE_jbuf = False
    policies: WheelPolicies | None = None

    with InGenericPkgCtx(wheel_fn) as ctx:
        shared_libraries_in_purelib = []
        shared_libraries_with_invalid_machine = []

        platform_wheel = False
        for fn, elf in elf_file_filter(ctx.iter_files()):
            # Check for invalid binary wheel format: no shared library should
            # be found in purelib
            so_name = fn.name

            # If this is in purelib, add it to the list of shared libraries in
            # purelib
            if any(p.name == "purelib" for p in fn.parents):
                shared_libraries_in_purelib.append(so_name)

            # If at least one shared library exists in purelib, this is going
            # to fail and there's no need to do further checks
            if not shared_libraries_in_purelib:
                log.debug("processing: %s", fn)
                elftree = ldd(fn, exclude=exclude)

                try:
                    elf_arch = elftree.platform.baseline_architecture
                except ValueError:
                    shared_libraries_with_invalid_machine.append(so_name)
                    log.warning("ignoring: %s with unknown architecture", so_name)
                    continue
                if architecture is None:
                    log.info("setting architecture to %s", elf_arch.value)
                    architecture = elf_arch
                elif elf_arch != architecture.baseline:
                    shared_libraries_with_invalid_machine.append(so_name)
                    log.warning("ignoring: %s with %s architecture", so_name, elf_arch)
                    continue

                if elftree.libc is not None:
                    if libc is None:
                        log.info("setting libc to %s", elftree.libc)
                        libc = elftree.libc
                    elif libc != elftree.libc:
                        log.warning("ignoring: %s with %s libc", so_name, elftree.libc)
                        continue

                if policies is None and libc is not None and architecture is not None:
                    policies = WheelPolicies(libc=libc, arch=architecture)

                platform_wheel = True

                for key, value in elf_find_versioned_symbols(elf):
                    log.debug("key %s, value %s", key, value)
                    versioned_symbols[key].add(value)

                is_py_ext, py_ver = elf_is_python_extension(fn, elf)

                # If the ELF is a Python extention, we definitely need to
                # include its external dependencies.
                if is_py_ext:
                    if policies is None:
                        assert architecture is not None
                        assert libc is None
                        msg = f"couldn't detect libc for python extension {fn}"
                        raise InvalidLibc(msg)
                    full_elftree[fn] = elftree
                    uses_PyFPE_jbuf |= elf_references_PyFPE_jbuf(elf)
                    if py_ver == 2:
                        uses_ucs2_symbols |= any(
                            True for _ in elf_find_ucs2_symbols(elf)
                        )
                    full_external_refs[fn] = policies.lddtree_external_references(
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
            arch = None if architecture is None else architecture.value
            raise NonPlatformWheel(arch, shared_libraries_with_invalid_machine)

        # Get a list of all external libraries needed by ELFs in the wheel.
        needed_libs = {
            lib
            for elf in itertools.chain(full_elftree.values(), nonpy_elftree.values())
            for lib in elf.needed
        }

        if policies is None:
            # we have no python extensions, either we have shared libraries with
            # no dependencies on libc (unlikely) or a statically linked executable
            # let's fallback to the host libc
            assert architecture is not None
            assert libc is None
            libc = Libc.detect()
            log.warning("couldn't detect wheel libc, defaulting to %s", str(libc))
            policies = WheelPolicies(libc=libc, arch=architecture)

        for fn, elf_tree in nonpy_elftree.items():
            # If a non-pyextension ELF file is not needed by something else
            # inside the wheel, then it was not checked by the logic above and
            # we should walk its elftree.
            if fn.name not in needed_libs:
                full_elftree[fn] = elf_tree

            # Even if a non-pyextension ELF file is not needed, we
            # should include it as an external reference, because
            # it might require additional external libraries.
            full_external_refs[fn] = policies.lddtree_external_references(
                elf_tree, ctx.path
            )

    log.debug("full_elftree:\n%s", json.dumps(full_elftree))
    log.debug(
        "full_external_refs (will be repaired):\n%s", json.dumps(full_external_refs)
    )

    return WheelElfData(
        policies,
        full_elftree,
        full_external_refs,
        versioned_symbols,
        uses_ucs2_symbols,
        uses_PyFPE_jbuf,
    )


def get_external_libs(external_refs: dict[str, ExternalReference]) -> dict[Path, str]:
    """Get external library dependencies for all policies excluding the default
    linux policy
    :param external_refs: external references for all policies
    :return: {realpath: soname} e.g.
    {'/path/to/external_ref.so.1.2.3': 'external_ref.so.1'}
    """
    result: dict[Path, str] = {}
    for external_ref in external_refs.values():
        # linux tag (priority 0) has no white-list, do not analyze it
        if external_ref.policy.priority == 0:
            continue
        # go through all libs, retrieving their soname and realpath
        for libname, realpath in external_ref.libs.items():
            if realpath and realpath not in result:
                result[Path(realpath)] = libname
    return result


def get_versioned_symbols(libs: dict[Path, str]) -> dict[str, dict[str, set[str]]]:
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
    policies: WheelPolicies,
    versioned_symbols: dict[str, set[str]],
    external_versioned_symbols: dict[str, dict[str, set[str]]],
    external_refs: dict[str, ExternalReference],
) -> list[tuple[Policy, dict[str, set[str]]]]:
    """Get symbol policies
    Since white-list is different per policy, this function inspects
    versioned_symbol per policy when including external refs
    :param versioned_symbols: versioned symbols for the current wheel
    :param external_versioned_symbols: versioned symbols for external libs
    :param external_refs: external references for all policies
    :return: list of tuples of the form (policy, versioned_symbols),
    e.g. [(<Policy: manylinux...>, {'libc.so.6', set(['GLIBC_2.5'])})]
    """
    result = []
    for external_ref in external_refs.values():
        # skip the linux policy
        if external_ref.policy.priority == 0:
            continue
        policy_symbols = deepcopy(versioned_symbols)
        for soname in external_ref.libs:
            if soname not in external_versioned_symbols:
                continue
            ext_symbols = external_versioned_symbols[soname]
            for k in iter(ext_symbols):
                policy_symbols[k].update(ext_symbols[k])
        # if the white-list policy changed, we don't want to allow highest priority policy
        # than the current one, that is, only restrict to a lower priority policy
        found_policy = min(
            external_ref.policy, policies.versioned_symbols_policy(policy_symbols)
        )
        result.append((found_policy, policy_symbols))
    return result


def _get_machine_policy(
    policies: WheelPolicies,
    elftree_by_fn: dict[Path, DynamicExecutable],
    external_so_names: frozenset[str],
) -> Policy:
    result = policies.highest
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
        if policies.architecture.is_superset(extended_architecture):
            continue
        log.warning(
            "ELF file %r requires %r instruction set, not in %r",
            fn,
            extended_architecture.value,
            policies.architecture.value,
        )
        result = policies.linux

    return result


def analyze_wheel_abi(
    libc: Libc | None,
    architecture: Architecture | None,
    wheel_fn: Path,
    exclude: frozenset[str],
    disable_isa_ext_check: bool,
    allow_graft: bool,
) -> WheelAbIInfo:
    data = get_wheel_elfdata(libc, architecture, wheel_fn, exclude)
    policies = data.policies
    elftree_by_fn = data.full_elftree
    external_refs_by_fn = data.full_external_refs
    versioned_symbols = data.versioned_symbols

    external_refs: dict[str, ExternalReference] = {
        p.name: ExternalReference({}, {}, p) for p in policies
    }

    for fn in elftree_by_fn:
        update(external_refs, external_refs_by_fn[fn])

    log.debug("external reference info")
    log.debug(json.dumps(external_refs))

    external_libs = get_external_libs(external_refs)
    external_versioned_symbols = get_versioned_symbols(external_libs)
    symbol_policies = get_symbol_policies(
        policies, versioned_symbols, external_versioned_symbols, external_refs
    )
    symbol_policy = policies.versioned_symbols_policy(versioned_symbols)

    # let's keep the highest priority policy and
    # corresponding versioned_symbols
    symbol_policy, versioned_symbols = max(
        symbol_policies, key=lambda x: x[0], default=(symbol_policy, versioned_symbols)
    )

    ref_policy = max(
        (e.policy for e in external_refs.values() if len(e.libs) == 0),
        default=policies.linux,
    )

    blacklist_policy = max(
        (e.policy for e in external_refs.values() if len(e.blacklist) == 0),
        default=policies.linux,
    )

    if disable_isa_ext_check:
        machine_policy = policies.highest
    else:
        machine_policy = _get_machine_policy(
            policies, elftree_by_fn, frozenset(external_libs.values())
        )

    ucs_policy = policies.linux if data.uses_ucs2_symbols else policies.highest
    pyfpe_policy = policies.linux if data.uses_PyFPE_jbuf else policies.highest

    overall_policy = min(
        symbol_policy,
        ucs_policy,
        pyfpe_policy,
        blacklist_policy,
        machine_policy,
    )
    if not allow_graft:
        overall_policy = min(overall_policy, ref_policy)

    return WheelAbIInfo(
        policies,
        external_refs_by_fn,
        overall_policy,
        external_refs,
        ref_policy,
        versioned_symbols,
        symbol_policy,
        ucs_policy,
        pyfpe_policy,
        blacklist_policy,
        machine_policy,
    )


_T = TypeVar("_T", ExternalReference, Path | None)


def update(d: dict[str, _T], u: Mapping[str, _T]) -> None:
    for k, v in u.items():
        if isinstance(v, ExternalReference):
            assert k in d
            assert isinstance(d[k], ExternalReference)
            assert d[k].policy == v.policy
            # update blacklist
            for lib, symbols in v.blacklist.items():
                if lib not in d[k].blacklist:
                    d[k].blacklist[lib] = sorted(symbols)
                else:
                    d[k].blacklist[lib] = sorted(
                        set(d[k].blacklist[lib]) | set(symbols)
                    )
            # libs
            update(d[k].libs, v.libs)
        elif isinstance(v, (Path, type(None))):
            d[k] = u[k]
        else:
            msg = f"can't update {d} with {k}:{v}"
            raise RuntimeError(msg)
