import itertools
import logging
import os
import shutil
from os.path import exists, basename, abspath, isabs
from os.path import join as pjoin
from typing import Dict, Optional

from auditwheel.patcher import ElfPatcher
from .elfutils import elf_read_rpaths, elf_read_dt_needed
from .hashfile import hashfile
from .policy import get_replace_platforms
from .wheel_abi import get_wheel_elfdata
from .wheeltools import InWheelCtx, add_platforms

logger = logging.getLogger(__name__)


def repair_wheel(wheel_path: str, abi: str, lib_sdir: str, out_dir: str,
                 update_tags: bool, patcher: ElfPatcher) -> Optional[str]:

    external_refs_by_fn = get_wheel_elfdata(wheel_path)[1]

    # Do not repair a pure wheel, i.e. has no external refs
    if not external_refs_by_fn:
        return

    soname_map = {}  # type: Dict[str, str]
    if not isabs(out_dir):
        out_dir = abspath(out_dir)

    wheel_fname = basename(wheel_path)

    with InWheelCtx(wheel_path) as ctx:
        ctx.out_wheel = pjoin(out_dir, wheel_fname)

        # here, fn is a path to a python extension library in
        # the wheel, and v['libs'] contains its required libs
        for fn, v in external_refs_by_fn.items():
            # pkg_root should resolve to like numpy/ or scipy/
            # note that it's possible for the wheel to contain
            # more than one pkg, which is why we detect the pkg root
            # for each fn.
            pkg_root = fn.split(os.sep)[0]

            if pkg_root == fn:
                # this file is an extension that's not contained in a
                # directory -- just supposed to be directly in site-packages
                dest_dir = lib_sdir + pkg_root.split('.')[0]
            else:
                dest_dir = pjoin(pkg_root, lib_sdir)

            if not exists(dest_dir):
                os.mkdir(dest_dir)

            ext_libs = v[abi]['libs']  # type: Dict[str, str]
            for soname, src_path in ext_libs.items():
                if src_path is None:
                    raise ValueError(('Cannot repair wheel, because required '
                                      'library "%s" could not be located') %
                                     soname)

                new_soname, new_path = copylib(src_path, dest_dir, patcher)
                soname_map[soname] = (new_soname, new_path)
                patcher.replace_needed(fn, soname, new_soname)

            if len(ext_libs) > 0:
                patcher.set_rpath(fn, dest_dir)

        # we grafted in a bunch of libraries and modified their sonames, but
        # they may have internal dependencies (DT_NEEDED) on one another, so
        # we need to update those records so each now knows about the new
        # name of the other.
        for old_soname, (new_soname, path) in soname_map.items():
            needed = elf_read_dt_needed(path)
            for n in needed:
                if n in soname_map:
                    patcher.replace_needed(path, n, soname_map[n][0])

        if update_tags:
            ctx.out_wheel = add_platforms(ctx, [abi],
                                          get_replace_platforms(abi))
    return ctx.out_wheel


def copylib(src_path, dest_dir, patcher):
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

    with open(src_path, 'rb') as f:
        shorthash = hashfile(f)[:8]

    src_name = os.path.basename(src_path)
    base, ext = src_name.split('.', 1)
    if not base.endswith('-%s' % shorthash):
        new_soname = '%s-%s.%s' % (base, shorthash, ext)
    else:
        new_soname = src_name

    dest_path = os.path.join(dest_dir, new_soname)
    if os.path.exists(dest_path):
        return new_soname, dest_path

    logger.debug('Grafting: %s -> %s', src_path, dest_path)
    rpaths = elf_read_rpaths(src_path)
    shutil.copy2(src_path, dest_path)

    patcher.set_so_name(dest_path, new_soname)

    if any(itertools.chain(rpaths['rpaths'], rpaths['runpaths'])):
        patcher.set_rpath(dest_path, dest_dir)

    return new_soname, dest_path

