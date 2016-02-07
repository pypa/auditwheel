import os
import shutil
import itertools
from os.path import (exists, isdir, relpath, dirname, split, basename, abspath,
                     isabs)
from os.path import join as pjoin
from subprocess import check_call
from distutils.spawn import find_executable
from typing import Dict, Optional

from .wheeltools import InWheelCtx
from .wheel_abi import get_wheel_elfdata
from .elfutils import elf_read_rpaths, is_subdir


def repair_wheel(wheel_path: str, abi: str, lib_sdir: str, out_dir:
                 str) -> Optional[str]:

    external_refs_by_fn = get_wheel_elfdata(wheel_path)[1]
    if not isabs(out_dir):
        out_dir = abspath(out_dir)

    with InWheelCtx(wheel_path) as ctx:
        ctx.out_wheel = pjoin(out_dir, basename(wheel_path))

        # here, fn is a path to a python extension library in
        # the wheel, and v['libs'] contains its required libs
        for fn, v in external_refs_by_fn.items():
            # pkg_root should resolve to like numpy/ or scipy/
            # note that it's possible for the wheel to contain
            # more than one pkg, which is why we detect the pkg root
            # for each fn.
            pkg_root = fn.split(os.sep)[0]

            if pkg_root == fn:
                # this file is an extension that's not contained in a directory -- just supposed to
                # be directly in site-packages
                dest_dir = lib_sdir + pkg_root.split('.')[0]
            else:
                if not exists(pjoin(pkg_root, '__init__.py')):
                    raise RuntimeError('Is this wheel malformatted? Or a bug?')
                dest_dir = pjoin(pkg_root, lib_sdir)

            if not exists(dest_dir):
                os.mkdir(dest_dir)

            ext_libs = v[abi]['libs']  # type: Dict[str, str]
            for libname, src_path in ext_libs.items():
                if src_path is None:
                    raise ValueError(('Cannot repair wheel, because required '
                                      'library "%s" could not be located') %
                                     libname)

                dest_path = os.path.join(dest_dir, libname)
                if not os.path.exists(dest_path):
                    copylib(src_path, dest_path)

            if len(ext_libs) > 0:
                patchelf(fn, dest_dir)

    return ctx.out_wheel


def copylib(src_path, dest_path):
    # Copy the a shared library from the system (src_path) into the wheel
    # if the library has a RUNPATH/RPATH to it's current location on the
    # system, we also update that to point to its new location.

    print('Grafting: %s' % src_path)
    rpaths = elf_read_rpaths(src_path)
    shutil.copy2(src_path, dest_path)

    for rp in itertools.chain(rpaths['rpaths'], rpaths['runpaths']):
        if is_subdir(rp, os.path.dirname(src_path)):
            patchelf(dest_path, pjoin(dirname(dest_path), relpath(rp, dirname(src_path))))
            break


def patchelf(fn, libdir):
    if not find_executable('patchelf'):
        raise ValueError('Cannot find required utility `patchelf` in PATH')

    rpath = pjoin('$ORIGIN', relpath(libdir, dirname(fn)))
    print('Setting RPATH: %s to "%s"' % (fn, rpath))
    check_call(['patchelf', '--force-rpath', '--set-rpath', rpath, fn])
