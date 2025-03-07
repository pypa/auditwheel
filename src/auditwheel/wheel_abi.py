from __future__ import annotations

import functools
import itertools
import logging
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TypeVar

from elftools.elf.elffile import ELFFile

from auditwheel.pool import POOL

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
from .policy import ExternalReference, Policy, WheelPolicies

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WheelAbIInfo:
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
    full_elftree: dict[Path, DynamicExecutable]
    full_external_refs: dict[Path, dict[str, ExternalReference]]
    versioned_symbols: dict[str, set[str]]
    uses_ucs2_symbols: bool
    uses_PyFPE_jbuf: bool


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
def get_wheel_elfdata(
    wheel_policy: WheelPolicies, wheel_fn: Path, exclude: frozenset[str]
) -> WheelElfData:
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

        def inner(fn: Path) -> None:
            nonlocal \
                platform_wheel, \
                shared_libraries_in_purelib, \
                uses_ucs2_symbols, \
                uses_PyFPE_jbuf

            with open(fn, "rb") as f:
                elf = ELFFile(f)

                so_name = fn.name

                log.debug("processing: %s", fn)
                elftree = ldd(fn, exclude=exclude)

                try:
                    arch = elftree.platform.baseline_architecture
                    if arch != wheel_policy.architecture.baseline:
                        shared_libraries_with_invalid_machine.append(so_name)
                        log.warning("ignoring: %s with %s architecture", so_name, arch)
                        return
                except ValueError:
                    shared_libraries_with_invalid_machine.append(so_name)
                    log.warning("ignoring: %s with unknown architecture", so_name)
                    return

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

        # Create new ELFFile object to avoid use-after-free
        for fn, _elf in elf_file_filter(ctx.iter_files()):
            # Check for invalid binary wheel format: no shared library should
            # be found in purelib
            so_name = fn.name

            # If this is in purelib, add it to the list of shared libraries in
            # purelib
            if any(p.name == "purelib" for p in fn.parents):
                shared_libraries_in_purelib.append(so_name)

            if not shared_libraries_in_purelib:
                POOL.submit(fn, inner, fn)

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

        POOL.wait()

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
            if fn.name not in needed_libs:
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

    return WheelElfData(
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
    wheel_policy: WheelPolicies,
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
        result.append(
            (wheel_policy.versioned_symbols_policy(policy_symbols), policy_symbols)
        )
    return result


def _get_machine_policy(
    wheel_policy: WheelPolicies,
    elftree_by_fn: dict[Path, DynamicExecutable],
    external_so_names: frozenset[str],
) -> Policy:
    result = wheel_policy.highest
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
        result = wheel_policy.lowest

    return result


def analyze_wheel_abi(
    wheel_policy: WheelPolicies,
    wheel_fn: Path,
    exclude: frozenset[str],
    disable_isa_ext_check: bool,
) -> WheelAbIInfo:
    external_refs: dict[str, ExternalReference] = {
        p.name: ExternalReference({}, {}, p) for p in wheel_policy.policies
    }

    elf_data = get_wheel_elfdata(wheel_policy, wheel_fn, exclude)
    elftree_by_fn = elf_data.full_elftree
    external_refs_by_fn = elf_data.full_external_refs
    versioned_symbols = elf_data.versioned_symbols
    has_ucs2 = elf_data.uses_ucs2_symbols
    uses_PyFPE_jbuf = elf_data.uses_PyFPE_jbuf

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
        (e.policy for e in external_refs.values() if len(e.libs) == 0),
        default=wheel_policy.lowest,
    )

    blacklist_policy = max(
        (e.policy for e in external_refs.values() if len(e.blacklist) == 0),
        default=wheel_policy.lowest,
    )

    if disable_isa_ext_check:
        machine_policy = wheel_policy.highest
    else:
        machine_policy = _get_machine_policy(
            wheel_policy, elftree_by_fn, frozenset(external_libs.values())
        )

    ucs_policy = wheel_policy.lowest if has_ucs2 else wheel_policy.highest
    pyfpe_policy = wheel_policy.lowest if uses_PyFPE_jbuf else wheel_policy.highest

    overall_policy = min(
        symbol_policy,
        ref_policy,
        ucs_policy,
        pyfpe_policy,
        blacklist_policy,
        machine_policy,
    )

    return WheelAbIInfo(
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


_T = TypeVar("_T", ExternalReference, Optional[Path])


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
