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

from elftools.elf.constants import E_FLAGS
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import NoteSection

from .architecture import Architecture
from .error import InvalidLibc
from .libc import Libc

log = logging.getLogger(__name__)
__all__ = ["DynamicExecutable", "DynamicLibrary", "ldd"]


@dataclass(frozen=True)
class Platform:
    _elf_osabi: str
    _elf_class: int
    _elf_little_endian: bool
    _elf_machine: str
    _base_arch: Architecture | None
    _ext_arch: Architecture | None
    _error_msg: str | None

    def is_compatible(self, other: Platform) -> bool:
        os_abis = frozenset((self._elf_osabi, other._elf_osabi))
        compat_sets = (
            frozenset(f"ELFOSABI_{x}" for x in ("NONE", "SYSV", "GNU", "LINUX")),
        )
        return (
            (len(os_abis) == 1 or any(os_abis.issubset(x) for x in compat_sets))
            and self._elf_class == other._elf_class
            and self._elf_little_endian == other._elf_little_endian
            and self._elf_machine == other._elf_machine
        )

    @property
    def baseline_architecture(self) -> Architecture:
        if self._base_arch is not None:
            return self._base_arch
        raise ValueError(self._error_msg)

    @property
    def extended_architecture(self) -> Architecture | None:
        if self._error_msg is not None:
            raise ValueError(self._error_msg)
        return self._ext_arch


@dataclass(frozen=True)
class DynamicLibrary:
    soname: str
    path: str | None
    realpath: Path | None
    platform: Platform | None = None
    needed: tuple[str, ...] = ()


@dataclass(frozen=True)
class DynamicExecutable:
    interpreter: str | None
    libc: Libc | None
    path: str
    realpath: Path
    platform: Platform
    needed: tuple[str, ...]
    rpath: tuple[str, ...]
    runpath: tuple[str, ...]
    libraries: dict[str, DynamicLibrary]


def _get_platform(elf: ELFFile) -> Platform:
    elf_osabi = elf.header["e_ident"]["EI_OSABI"]
    elf_class = elf.elfclass
    elf_little_endian = elf.little_endian
    elf_machine = elf["e_machine"]
    base_arch = {
        ("EM_386", 32, True): Architecture.i686,
        ("EM_X86_64", 64, True): Architecture.x86_64,
        ("EM_PPC64", 64, True): Architecture.ppc64le,
        ("EM_PPC64", 64, False): Architecture.ppc64,
        ("EM_RISCV", 64, True): Architecture.riscv64,
        ("EM_AARCH64", 64, True): Architecture.aarch64,
        ("EM_S390", 64, False): Architecture.s390x,
        ("EM_ARM", 32, True): Architecture.armv7l,
        ("EM_LOONGARCH", 64, True): Architecture.loongarch64,
    }.get((elf_machine, elf_class, elf_little_endian), None)
    ext_arch: Architecture | None = None
    error_msg: str | None = None
    flags = elf["e_flags"]
    assert base_arch is None or base_arch.baseline == base_arch
    if base_arch is None:
        error_msg = "Unknown architecture"
    elif base_arch == Architecture.x86_64:
        for section in elf.iter_sections():
            if not isinstance(section, NoteSection):
                continue
            for note in section.iter_notes():
                if note["n_type"] != "NT_GNU_PROPERTY_TYPE_0":
                    continue
                if note["n_name"] != "GNU":
                    continue
                for prop in note["n_desc"]:
                    if prop.pr_type != "GNU_PROPERTY_X86_ISA_1_NEEDED":
                        continue
                    if prop.pr_datasz != 4:
                        continue
                    data = prop.pr_data
                    data -= data & 1  # clear baseline
                    if data & 8 == 8:
                        ext_arch = Architecture.x86_64_v4
                        break
                    if data & 4 == 4:
                        ext_arch = Architecture.x86_64_v3
                        break
                    if data & 2 == 2:
                        ext_arch = Architecture.x86_64_v2
                        break
                    if data != 0:
                        error_msg = "unknown x86_64 ISA"
                break
    elif base_arch == Architecture.armv7l:
        if (flags & E_FLAGS.EF_ARM_EABIMASK) != E_FLAGS.EF_ARM_EABI_VER5:
            error_msg = "Invalid ARM EABI version for armv7l"
        elif (flags & E_FLAGS.EF_ARM_ABI_FLOAT_HARD) != E_FLAGS.EF_ARM_ABI_FLOAT_HARD:
            error_msg = "armv7l shall use hard-float"
        if error_msg is not None:
            base_arch = None

    return Platform(
        elf_osabi,
        elf_class,
        elf_little_endian,
        elf_machine,
        base_arch,
        ext_arch,
        error_msg,
    )


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
def load_ld_paths(
    libc: Libc | None, root: str = "/", prefix: str = ""
) -> dict[str, list[str]]:
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
    ldpaths: dict[str, list[str]] = {"conf": [], "env": [], "interp": []}

    # Load up $LD_LIBRARY_PATH.
    env_ldpath = os.environ.get("LD_LIBRARY_PATH")
    if env_ldpath is not None:
        if root != "/":
            log.warning("ignoring LD_LIBRARY_PATH due to ROOT usage")
        else:
            # XXX: If this contains $ORIGIN, we probably have to parse this
            # on a per-ELF basis so it can get turned into the right thing.
            ldpaths["env"] = parse_ld_paths(env_ldpath, path="")

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


def find_lib(
    platform: Platform, lib: str, ldpaths: list[str], root: str = "/"
) -> tuple[Path | None, str | None]:
    """Try to locate a ``lib`` that is compatible to ``elf`` in the given
    ``ldpaths``

    Parameters
    ----------
    platform : Platform
        The platform which the library should be compatible with (ELF wise)
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
        target = Path(readlink(path, root, prefixed=True))

        if target.exists():
            with open(target, "rb") as f:
                libelf = ELFFile(f)
                if platform.is_compatible(_get_platform(libelf)):
                    return target, path

    return None, None


def ldd(
    path: Path,
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
    _first = _all_libs is None
    if _all_libs is None:
        _all_libs = {}

    log.debug("ldd(%s)", path)

    interpreter: str | None = None
    libc: Libc | None = None
    needed: list[str] = []
    rpaths: list[str] = []
    runpaths: list[str] = []

    with open(path, "rb") as f:
        elf = ELFFile(f)

        # get the platform
        platform = _get_platform(elf)

        # If this is the first ELF, extract the interpreter.
        if _first:
            for segment in elf.iter_segments():
                if segment.header.p_type != "PT_INTERP":
                    continue
                interp = segment.get_interp_name()
                log.debug("  interp           = %s", interp)
                interpreter = normpath(root + interp)
                soname = os.path.basename(interpreter)
                _all_libs[soname] = DynamicLibrary(
                    soname,
                    interpreter,
                    Path(readlink(interpreter, root, prefixed=True)),
                    platform,
                )
                # if we have an interpreter and it's not MUSL, assume GLIBC
                libc = Libc.MUSL if soname.startswith("ld-musl-") else Libc.GLIBC
                if ldpaths is None:
                    ldpaths = load_ld_paths(libc).copy()
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
                    rpaths = parse_ld_paths(t.rpath, path=str(path), root=root)
                elif t.entry.d_tag == "DT_RUNPATH":
                    runpaths = parse_ld_paths(t.runpath, path=str(path), root=root)
                elif t.entry.d_tag == "DT_NEEDED":
                    needed.append(t.needed)
            if runpaths:
                # If both RPATH and RUNPATH are set, only the latter is used.
                rpaths = []

            # XXX: We assume there is only one PT_DYNAMIC.  This is
            # probably fine since the runtime ldso does the same.
            break

        del elf

    if _first:
        # get the libc based on dependencies
        for soname in needed:
            if soname.startswith(("libc.musl-", "ld-musl-")):
                if libc is None:
                    libc = Libc.MUSL
                if libc != Libc.MUSL:
                    msg = f"found a dependency on MUSL but the libc is already set to {libc}"
                    raise InvalidLibc(msg)
            elif soname == "libc.so.6" or soname.startswith(("ld-linux-", "ld64.so.")):
                if libc is None:
                    libc = Libc.GLIBC
                if libc != Libc.GLIBC:
                    msg = f"found a dependency on GLIBC but the libc is already set to {libc}"
                    raise InvalidLibc(msg)
        if libc is None:
            # try the filename as a last resort
            if path.name.endswith(("-arm-linux-musleabihf.so", "-linux-musl.so")):
                libc = Libc.MUSL
            elif path.name.endswith(("-arm-linux-gnueabihf.so", "-linux-gnu.so")):
                # before python 3.11, musl was also using gnu
                soabi = path.stem.split(".")[-1].split("-")
                valid_python = tuple(f"3{minor}" for minor in range(11, 100))
                if soabi[0] == "cpython" and soabi[1].startswith(valid_python):
                    libc = Libc.GLIBC

        if ldpaths is None:
            ldpaths = load_ld_paths(libc).copy()
        # Propagate the rpaths used by the main ELF since those will be
        # used at runtime to locate things.
        ldpaths["rpath"] = rpaths
        ldpaths["runpath"] = runpaths
        log.debug("  ldpaths[rpath]   = %s", rpaths)
        log.debug("  ldpaths[runpath] = %s", runpaths)

    assert ldpaths is not None

    all_ldpaths = (
        ldpaths["rpath"]
        + rpaths
        + runpaths
        + ldpaths["env"]
        + ldpaths["runpath"]
        + ldpaths["conf"]
        + ldpaths["interp"]
    )
    _excluded_libs: set[str] = set()
    for soname in needed:
        if soname in _all_libs:
            continue
        if soname in _excluded_libs:
            continue
        if any(fnmatch(soname, e) for e in exclude):
            log.info("Excluding %s", soname)
            _excluded_libs.add(soname)
            continue
        realpath, fullpath = find_lib(platform, soname, all_ldpaths, root)
        if realpath is not None and any(fnmatch(str(realpath), e) for e in exclude):
            log.info("Excluding %s", realpath)
            _excluded_libs.add(soname)
            continue
        _all_libs[soname] = DynamicLibrary(soname, fullpath, realpath)
        if realpath is None or fullpath is None:
            continue
        dependency = ldd(realpath, root, prefix, ldpaths, fullpath, exclude, _all_libs)
        _all_libs[soname] = DynamicLibrary(
            soname,
            fullpath,
            realpath,
            dependency.platform,
            dependency.needed,
        )

    return DynamicExecutable(
        interpreter,
        libc,
        str(path) if display is None else display,
        path,
        platform,
        tuple(soname for soname in needed if soname not in _excluded_libs),
        tuple(rpaths),
        tuple(runpaths),
        _all_libs,
    )
