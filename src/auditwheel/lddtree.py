# Copyright 2016 Robert McGibbon
# Copyright 2012-2014 Gentoo Foundation
# Copyright 2012-2014 Mike Frysinger <vapier@gentoo.org>
# Copyright 2012-2014 The Chromium OS Authors
# Use of this source code is governed by a BSD-style license (BSD-3)
# Original version available from:
#   https://sources.gentoo.org/cgi-bin/viewvc.cgi/gentoo-projects/pax-utils/lddtree.py
"""Read the ELF dependency tree

This does not work like `ldd` in that we do not execute/load code (only read
files on disk).
"""

from __future__ import annotations

import errno
import functools
import glob
import logging
import os
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from elftools.elf.elffile import ELFFile

from .libc import Libc, get_libc

log = logging.getLogger(__name__)
__all__ = ["DynamicExecutable", "DynamicLibrary", "ldd"]


@dataclass(frozen=True)
class DynamicLibrary:
    soname: str
    path: str | None
    realpath: str | None
    needed: frozenset[str] = frozenset()


@dataclass(frozen=True)
class DynamicExecutable:
    interpreter: str | None
    path: str
    realpath: str
    needed: frozenset[str]
    rpath: tuple[str, ...]
    runpath: tuple[str, ...]
    libraries: dict[str, DynamicLibrary]


def normpath(path: str) -> str:
    """Normalize a path

    Python's os.path.normpath() doesn't handle some cases:
    // -> //
    //..// -> //
    //..//..// -> ///
    """
    return os.path.normpath(path).replace("//", "/")


def readlink(path: str, root: str, prefixed: bool = False) -> str:
    """Like os.readlink(), but relative to a ``root``

    This does not currently handle the pathological case:
    /lib/foo.so -> ../../../../../../../foo.so
    This relies on the .. entries in / to point to itself.

    Parameters
    ----------
    path
        The symlink to read
    root
        The path to use for resolving absolute symlinks
    prefixed
        When False, the ``path`` must not have ``root`` prefixed to it, nor
        will the return value have ``root`` prefixed.  When True, ``path``
        must have ``root`` prefixed, and the return value will have ``root``
        added.

    Returns
    -------
    A fully resolved symlink path
    """
    root = root.rstrip("/")
    if prefixed:
        path = path[len(root) :]

    while os.path.islink(root + path):
        path = os.path.join(os.path.dirname(path), os.readlink(root + path))

    return normpath((root + path) if prefixed else path)


def dedupe(items: list[str]) -> list[str]:
    """Remove all duplicates from ``items`` (keeping order)"""
    seen: dict[str, str] = {}
    return [seen.setdefault(x, x) for x in items if x not in seen]


def parse_ld_paths(str_ldpaths: str, path: str, root: str = "") -> list[str]:
    """Parse the colon-delimited list of paths and apply ldso rules to each

    Note the special handling as dictated by the ldso:
    - Empty paths are equivalent to $PWD
    - $ORIGIN is expanded to the path of the given file
    - (TODO) $LIB and friends

    Parameters
    ----------
    str_ldpaths
        A colon-delimited string of paths
    root
        The path to prepend to all paths found
    path
        The object actively being parsed (used for $ORIGIN)

    Returns
    -------
        list of processed paths
    """
    ldpaths: list[str] = []
    for ldpath in str_ldpaths.split(":"):
        if ldpath == "":
            # The ldso treats "" paths as $PWD.
            ldpath_ = os.getcwd()
        elif "$ORIGIN" in ldpath:
            ldpath_ = ldpath.replace("$ORIGIN", os.path.dirname(os.path.abspath(path)))
        else:
            ldpath_ = root + ldpath
        ldpaths.append(normpath(ldpath_))
    return [p for p in dedupe(ldpaths) if os.path.isdir(p)]


@functools.lru_cache
def parse_ld_so_conf(ldso_conf: str, root: str = "/", _first: bool = True) -> list[str]:
    """Load all the paths from a given ldso config file

    This should handle comments, whitespace, and "include" statements.

    Parameters
    ----------
    ldso_conf
        The file to scan
    root
        The path to prepend to all paths found
    _first
        Recursive use only; is this the first ELF?

    Returns
    -------
    list of paths found
    """
    paths: list[str] = []

    dbg_pfx = "" if _first else "  "
    try:
        log.debug("%sparse_ld_so_conf(%s)", dbg_pfx, ldso_conf)
        with open(ldso_conf) as f:
            for input_line in f.readlines():
                line = input_line.split("#", 1)[0].strip()
                if not line:
                    continue
                if line.startswith("include "):
                    line = line[8:]
                    if line[0] == "/":
                        line = root + line.lstrip("/")
                    else:
                        line = os.path.dirname(ldso_conf) + "/" + line
                    log.debug("%s  glob: %s", dbg_pfx, line)
                    for path in glob.glob(line):
                        paths += parse_ld_so_conf(path, root=root, _first=False)
                else:
                    paths += [normpath(root + line)]
    except OSError as e:
        if e.errno != errno.ENOENT:
            log.warning(e)

    if _first:
        # XXX: Load paths from ldso itself.
        # Remove duplicate entries to speed things up.
        paths = [p for p in dedupe(paths) if os.path.isdir(p)]

    return paths


@functools.lru_cache
def load_ld_paths(root: str = "/", prefix: str = "") -> dict[str, list[str]]:
    """Load linker paths from common locations

    This parses the ld.so.conf and LD_LIBRARY_PATH env var.

    Parameters
    ----------
    root
        The root tree to prepend to paths
    prefix
        The path under ``root`` to search

    Returns
    -------
    dict containing library paths to search
    """
    ldpaths: dict = {"conf": [], "env": [], "interp": []}

    # Load up $LD_LIBRARY_PATH.
    env_ldpath = os.environ.get("LD_LIBRARY_PATH")
    if env_ldpath is not None:
        if root != "/":
            log.warning("ignoring LD_LIBRARY_PATH due to ROOT usage")
        else:
            # XXX: If this contains $ORIGIN, we probably have to parse this
            # on a per-ELF basis so it can get turned into the right thing.
            ldpaths["env"] = parse_ld_paths(env_ldpath, path="")

    libc = get_libc()
    if libc == Libc.MUSL:
        # from https://git.musl-libc.org/cgit/musl/tree/ldso
        # /dynlink.c?id=3f701faace7addc75d16dea8a6cd769fa5b3f260#n1063
        root_prefix = Path(root) / prefix
        ld_musl = list((root_prefix / "etc").glob("ld-musl-*.path"))
        assert len(ld_musl) <= 1
        if len(ld_musl) == 0:
            ldpaths["conf"] = [
                root + "/lib",
                root + "/usr/local/lib",
                root + "/usr/lib",
            ]
        else:
            ldpaths["conf"] = []
            for ldpath in ld_musl[0].read_text().split(":"):
                ldpath_stripped = ldpath.strip()
                if ldpath_stripped == "":
                    continue
                ldpaths["conf"].append(root + ldpath_stripped)
    else:
        # Load up /etc/ld.so.conf.
        ldpaths["conf"] = parse_ld_so_conf(root + prefix + "/etc/ld.so.conf", root=root)
        # the trusted directories are not necessarily in ld.so.conf
        ldpaths["conf"].extend(["/lib", "/lib64/", "/usr/lib", "/usr/lib64"])
    log.debug("linker ldpaths: %s", ldpaths)
    return ldpaths


def compatible_elfs(elf1: ELFFile, elf2: ELFFile) -> bool:
    """See if two ELFs are compatible

    This compares the aspects of the ELF to see if they're compatible:
    bit size, endianness, machine type, and operating system.

    Parameters
    ----------
    elf1 : ELFFile
    elf2 : ELFFile

    Returns
    -------
    True if compatible, False otherwise
    """
    osabis = frozenset(e.header["e_ident"]["EI_OSABI"] for e in (elf1, elf2))
    compat_sets = (
        frozenset(f"ELFOSABI_{x}" for x in ("NONE", "SYSV", "GNU", "LINUX")),
    )
    return (
        (len(osabis) == 1 or any(osabis.issubset(x) for x in compat_sets))
        and elf1.elfclass == elf2.elfclass
        and elf1.little_endian == elf2.little_endian
        and elf1.header["e_machine"] == elf2.header["e_machine"]
    )


def find_lib(
    elf: ELFFile, lib: str, ldpaths: list[str], root: str = "/"
) -> tuple[str | None, str | None]:
    """Try to locate a ``lib`` that is compatible to ``elf`` in the given
    ``ldpaths``

    Parameters
    ----------
    elf : ELFFile
        The elf which the library should be compatible with (ELF wise)
    lib : str
        The library (basename) to search for
    ldpaths : list[str]
        A list of paths to search
    root : str
       The root path to resolve symlinks

    Returns
    -------
    Tuple of the full path to the desired library and the real path to it
    """

    for ldpath in ldpaths:
        path = os.path.join(ldpath, lib)
        target = readlink(path, root, prefixed=True)

        if os.path.exists(target):
            with open(target, "rb") as f:
                libelf = ELFFile(f)
                if compatible_elfs(elf, libelf):
                    return target, path

    return None, None


def ldd(
    path: str,
    root: str = "/",
    prefix: str = "",
    ldpaths: dict[str, list[str]] | None = None,
    display: str | None = None,
    exclude: frozenset[str] = frozenset(),
    _all_libs: dict[str, DynamicLibrary] | None = None,
) -> DynamicExecutable:
    """Parse the ELF dependency tree of the specified file

    Parameters
    ----------
    path
        The ELF to scan
    root
        The root tree to prepend to paths; this applies to interp and rpaths
        only as ``path`` and ``ldpaths`` are expected to be prefixed already
    prefix
        The path under ``root`` to search
    ldpaths
        dict containing library paths to search; should have the keys:
        conf, env, interp. If not supplied, the function ``load_ld_paths``
        will be called.
    display
        The path to show rather than ``path``
    exclude
        List of soname (DT_NEEDED) to exclude from the tree
    _all_libs
        Recursive use only; dict of all libs we've seen

    Returns
    -------
    a dict containing information about all the ELFs; e.g.
    {
      'interp': '/lib64/ld-linux.so.2',
      'needed': ['libc.so.6', 'libcurl.so.4',],
      'libs': {
        'libc.so.6': {
          'path': '/lib64/libc.so.6',
          'needed': [],
        },
        'libcurl.so.4': {
          'path': '/usr/lib64/libcurl.so.4',
          'needed': ['libc.so.6', 'librt.so.1',],
        },
      },
    }
    """
    if not ldpaths:
        ldpaths = load_ld_paths().copy()

    _first = _all_libs is None
    if _all_libs is None:
        _all_libs = {}

    log.debug("ldd(%s)", path)

    interpreter: str | None = None
    needed: set[str] = set()
    rpaths: list[str] = []
    runpaths: list[str] = []
    _excluded_libs: set[str] = set()

    with open(path, "rb") as f:
        elf = ELFFile(f)

        # If this is the first ELF, extract the interpreter.
        if _first:
            for segment in elf.iter_segments():
                if segment.header.p_type != "PT_INTERP":
                    continue

                interp = segment.get_interp_name()
                log.debug("  interp           = %s", interp)
                interpreter = normpath(root + interp)
                # XXX: Should read it and scan for /lib paths.
                ldpaths["interp"] = [
                    normpath(root + os.path.dirname(interp)),
                    normpath(
                        root + prefix + "/usr" + os.path.dirname(interp).lstrip(prefix)
                    ),
                ]
                log.debug("  ldpaths[interp]  = %s", ldpaths["interp"])
                break

        # Parse the ELF's dynamic tags.
        for segment in elf.iter_segments():
            if segment.header.p_type != "PT_DYNAMIC":
                continue

            for t in segment.iter_tags():
                if t.entry.d_tag == "DT_RPATH":
                    rpaths = parse_ld_paths(t.rpath, path=path, root=root)
                elif t.entry.d_tag == "DT_RUNPATH":
                    runpaths = parse_ld_paths(t.runpath, path=path, root=root)
                elif t.entry.d_tag == "DT_NEEDED":
                    needed.add(t.needed)
            if runpaths:
                # If both RPATH and RUNPATH are set, only the latter is used.
                rpaths = []

            # XXX: We assume there is only one PT_DYNAMIC.  This is
            # probably fine since the runtime ldso does the same.
            break

        if _first:
            # Propagate the rpaths used by the main ELF since those will be
            # used at runtime to locate things.
            ldpaths["rpath"] = rpaths
            ldpaths["runpath"] = runpaths
            log.debug("  ldpaths[rpath]   = %s", rpaths)
            log.debug("  ldpaths[runpath] = %s", runpaths)

        # Search for the libs this ELF uses.
        all_ldpaths = (
            ldpaths["rpath"]
            + rpaths
            + runpaths
            + ldpaths["env"]
            + ldpaths["runpath"]
            + ldpaths["conf"]
            + ldpaths["interp"]
        )
        for soname in needed:
            if soname in _all_libs:
                continue
            if soname in _excluded_libs:
                continue
            if any(fnmatch(soname, e) for e in exclude):
                log.info("Excluding %s", soname)
                _excluded_libs.add(soname)
                continue
            # TODO we should avoid keeping elf here, related to compat
            realpath, fullpath = find_lib(elf, soname, all_ldpaths, root)
            if realpath is not None and any(fnmatch(realpath, e) for e in exclude):
                log.info("Excluding %s", realpath)
                _excluded_libs.add(soname)
                continue
            _all_libs[soname] = DynamicLibrary(soname, fullpath, realpath)
            if realpath is None or fullpath is None:
                continue
            lret = ldd(
                realpath,
                root,
                prefix,
                ldpaths,
                display=fullpath,
                exclude=exclude,
                _all_libs=_all_libs,
            )
            _all_libs[soname] = DynamicLibrary(
                soname, fullpath, realpath, lret.needed
            )

        del elf

    if interpreter is not None:
        soname = os.path.basename(interpreter)
        _all_libs[soname] = DynamicLibrary(
            soname, interpreter, readlink(interpreter, root, prefixed=True)
        )

    return DynamicExecutable(
        interpreter,
        path if display is None else display,
        path,
        frozenset(needed - _excluded_libs),
        tuple(rpaths),
        tuple(runpaths),
        _all_libs,
    )
