from __future__ import annotations

from contextlib import ExitStack
import itertools
import logging
import os
import platform
import re
import shutil
import stat
from collections.abc import Iterable
from fnmatch import fnmatch
from os.path import isabs
from pathlib import Path
from subprocess import check_call
from concurrent.futures import ThreadPoolExecutor, Future, as_completed

from auditwheel.patcher import ElfPatcher

from .elfutils import elf_read_dt_needed, elf_read_rpaths, is_subdir
from .hashfile import hashfile
from .policy import WheelPolicies, get_replace_platforms
from .wheel_abi import get_wheel_elfdata
from .wheeltools import InWheelCtx, add_platforms

logger = logging.getLogger(__name__)


# Copied from wheel 0.31.1
WHEEL_INFO_RE = re.compile(
    r"""^(?P<namever>(?P<name>.+?)-(?P<ver>\d.*?))(-(?P<build>\d.*?))?
     -(?P<pyver>[a-z].+?)-(?P<abi>.+?)-(?P<plat>.+?)(\.whl|\.dist-info)$""",
    re.VERBOSE,
).match


def repair_wheel(
    wheel_policy: WheelPolicies,
    wheel_path: Path,
    abis: list[str],
    lib_sdir: str,
    out_dir: Path,
    update_tags: bool,
    patcher: ElfPatcher,
    exclude: frozenset[str],
    strip: bool = False,
) -> Path | None:
    elf_data = get_wheel_elfdata(wheel_policy, wheel_path, exclude)
    external_refs_by_fn = elf_data.full_external_refs

    # Do not repair a pure wheel, i.e. has no external refs
    if not external_refs_by_fn:
        return None

    soname_map: dict[str, tuple[str, Path]] = {}

    out_dir = out_dir.resolve(strict=True)
    wheel_fname = wheel_path.name

    with InWheelCtx(wheel_path) as ctx:
        ctx.out_wheel = out_dir / wheel_fname

        match = WHEEL_INFO_RE(wheel_fname)
        if not match:
            msg = f"Failed to parse wheel file name: {wheel_fname}"
            raise ValueError(msg)

        dest_dir = Path(match.group("name") + lib_sdir)
        if not dest_dir.exists():
            dest_dir.mkdir()

        pool = ThreadPoolExecutor()
        copy_works: dict[str, Future] = {}
        replace_works: dict[str, Future] = {}

        # here, fn is a path to an ELF file (lib or executable) in
        # the wheel, and v['libs'] contains its required libs
        for fn, v in external_refs_by_fn.items():
            ext_libs = v[abis[0]].libs
            replacements: list[tuple[str, str]] = []
            for soname, src_path in ext_libs.items():
                assert not any(fnmatch(soname, e) for e in exclude)

                if src_path is None:
                    msg = (
                        "Cannot repair wheel, because required "
                        f'library "{soname}" could not be located'
                    )
                    raise ValueError(msg)

                new_soname, new_path = copylib(src_path, dest_dir, patcher, dry=True)
                if not new_path.exists() and str(new_path) not in copy_works:
                    copy_works[str(new_path)] = pool.submit(copylib, src_path, dest_dir, patcher)
                soname_map[soname] = (new_soname, new_path)
                replacements.append((soname, new_soname))
            
            def _inner_replace():
                if replacements:
                    patcher.replace_needed(fn, *replacements)

                if len(ext_libs) > 0:
                    new_fn = fn
                    if _path_is_script(fn):
                        new_fn = _replace_elf_script_with_shim(match.group("name"), fn)

                    new_rpath = os.path.relpath(dest_dir, new_fn.parent)
                    new_rpath = os.path.join("$ORIGIN", new_rpath)
                    append_rpath_within_wheel(new_fn, new_rpath, ctx.name, patcher)

            replace_works[fn] = pool.submit(_inner_replace)

        # we grafted in a bunch of libraries and modified their sonames, but
        # they may have internal dependencies (DT_NEEDED) on one another, so
        # we need to update those records so each now knows about the new
        # name of the other.
        as_completed(copy_works.values())
        for _, path in soname_map.values():
            needed = elf_read_dt_needed(path)
            replacements = []
            for n in needed:
                if n in soname_map:
                    replacements.append((n, soname_map[n][0]))
            if replacements:
                pool.submit(patcher.replace_needed, path, *replacements)

        if update_tags:
            ctx.out_wheel = add_platforms(ctx, abis, get_replace_platforms(abis[0]))

        if strip:
            for lib, future in itertools.chain(copy_works.items(), replace_works.items()):                
                logger.info("Stripping symbols from %s", lib)
                then(future, check_call, ["strip", "-s", lib])

        pool.shutdown()

    return ctx.out_wheel


def then(pool: ThreadPoolExecutor, future: Future, *args, **kwargs):
    future.result()
    pool.submit(*args, **kwargs)


def copylib(src_path: Path, dest_dir: Path, patcher: ElfPatcher, dry: bool = False) -> tuple[str, Path]:
    """Graft a shared library from the system into the wheel and update the
    relevant links.

    1) Copy the file from src_path to dest_dir/
    2) Rename the shared object from soname to soname.<unique>
    3) If the library has a RUNPATH/RPATH, clear it and set RPATH to point to
    its new location.
    """
    # Copy the a shared library from the system (src_path) into the wheel
    # if the library has a RUNPATH/RPATH we clear it and set RPATH to point to
    # its new location.

    with open(src_path, "rb") as f:
        shorthash = hashfile(f)[:8]

    src_name = src_path.name
    base, ext = src_name.split(".", 1)
    if not base.endswith(f"-{shorthash}"):
        new_soname = f"{base}-{shorthash}.{ext}"
    else:
        new_soname = src_name

    dest_path = dest_dir / new_soname
    if dry or dest_path.exists():
        return new_soname, dest_path

    logger.debug("Grafting: %s -> %s", src_path, dest_path)
    rpaths = elf_read_rpaths(src_path)
    shutil.copy2(src_path, dest_path)
    statinfo = dest_path.stat()
    if not statinfo.st_mode & stat.S_IWRITE:
        os.chmod(dest_path, statinfo.st_mode | stat.S_IWRITE)

    patcher.set_soname(dest_path, new_soname)

    if any(itertools.chain(rpaths["rpaths"], rpaths["runpaths"])):
        patcher.set_rpath(dest_path, "$ORIGIN")

    return new_soname, dest_path


def append_rpath_within_wheel(
    lib_name: Path, rpath: str, wheel_base_dir: Path, patcher: ElfPatcher
) -> None:
    """Add a new rpath entry to a file while preserving as many existing
    rpath entries as possible.

    In order to preserve an rpath entry it must:

    1) Point to a location within wheel_base_dir.
    2) Not be a duplicate of an already-existing rpath entry.
    """
    if not lib_name.is_absolute():
        lib_name = lib_name.absolute()
    lib_dir = lib_name.parent
    if not wheel_base_dir.is_absolute():
        wheel_base_dir = wheel_base_dir.absolute()

    def is_valid_rpath(rpath: str) -> bool:
        return _is_valid_rpath(rpath, lib_dir, wheel_base_dir)

    old_rpaths = patcher.get_rpath(lib_name)
    rpaths = filter(is_valid_rpath, old_rpaths.split(":"))
    # Remove duplicates while preserving ordering
    # Fake an OrderedSet using a dict (ordered in python 3.7+)
    rpath_set = {old_rpath: "" for old_rpath in rpaths}
    rpath_set[rpath] = ""

    patcher.set_rpath(lib_name, ":".join(rpath_set))


def _is_valid_rpath(rpath: str, lib_dir: Path, wheel_base_dir: Path) -> bool:
    full_rpath_entry = _resolve_rpath_tokens(rpath, lib_dir)
    if not isabs(full_rpath_entry):
        logger.debug(
            "rpath entry %s could not be resolved to an absolute path -- discarding it.",
            rpath,
        )
        return False
    if not is_subdir(full_rpath_entry, wheel_base_dir):
        logger.debug("rpath entry %s points outside the wheel -- discarding it.", rpath)
        return False
    logger.debug("Preserved rpath entry %s", rpath)
    return True


def _resolve_rpath_tokens(rpath: str, lib_base_dir: Path) -> str:
    # See https://www.man7.org/linux/man-pages/man8/ld.so.8.html#DESCRIPTION
    system_lib_dir = "lib64" if platform.architecture()[0] == "64bit" else "lib"
    system_processor_type = platform.machine()
    token_replacements = {
        "ORIGIN": str(lib_base_dir),
        "LIB": system_lib_dir,
        "PLATFORM": system_processor_type,
    }
    for token, target in token_replacements.items():
        rpath = rpath.replace(f"${token}", target)  # $TOKEN
        rpath = rpath.replace(f"${{{token}}}", target)  # ${TOKEN}
    return rpath


def _path_is_script(path: Path) -> bool:
    # Looks something like "uWSGI-2.0.21.data/scripts/uwsgi"
    components = path.parts
    return (
        len(components) == 3
        and components[0].endswith(".data")
        and components[1] == "scripts"
    )


def _replace_elf_script_with_shim(package_name: str, orig_path: Path) -> Path:
    """Move an ELF script and replace it with a shim.

    We can't directly rewrite the RPATH of ELF executables in the "scripts"
    directory since scripts aren't installed to a consistent relative path to
    platlib files.

    Instead, we move the executable into a special directory in platlib and put
    a shim script in its place which execs the real executable.

    More context: https://github.com/pypa/auditwheel/issues/340

    Returns the new path of the moved executable.
    """
    scripts_dir = Path(f"{package_name}.scripts")
    scripts_dir.mkdir(exist_ok=True)

    new_path = scripts_dir / orig_path.name
    os.rename(orig_path, new_path)

    with open(orig_path, "w", newline="\n") as f:
        f.write(_script_shim(new_path))
    os.chmod(orig_path, os.stat(new_path).st_mode)

    return new_path


def _script_shim(binary_path: Path) -> str:
    return f"""\
#!python
import os
import sys
import sysconfig


if __name__ == "__main__":
    os.execv(
        os.path.join(sysconfig.get_path("platlib"), {binary_path.as_posix()!r}),
        sys.argv,
    )
"""
