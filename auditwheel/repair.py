import os
import re
import shutil
import itertools
import functools
from os.path import exists, relpath, dirname, basename, abspath, isabs
from os.path import join as pjoin
from subprocess import check_call, check_output, CalledProcessError
from distutils.spawn import find_executable
from typing import Optional

from .policy import get_replace_platforms
from .wheeltools import InWheelCtx, add_platforms
from .wheel_abi import get_wheel_elfdata
from .elfutils import elf_read_rpaths, is_subdir, elf_read_dt_needed
from .hashfile import hashfile


@functools.lru_cache()
def verify_patchelf():
    """This function looks for the ``patchelf`` external binary in the PATH,
    checks for the required version, and throws an exception if a proper
    version can't be found. Otherwise, silcence is golden
    """
    if not find_executable('patchelf'):
        raise ValueError('Cannot find required utility `patchelf` in PATH')
    try:
        version = check_output(['patchelf', '--version']).decode('utf-8')
    except CalledProcessError:
        raise ValueError('Could not call `patchelf` binary')

    m = re.match('patchelf\s+(\d+(.\d+)?)', version)
    if m and tuple(int(x) for x in m.group(1).split('.')) >= (0, 9):
        return
    raise ValueError(('patchelf %s found. auditwheel repair requires '
                      'patchelf >= 0.9.') %
                     version)


def repair_wheel(wheel_path: str, abi: str, lib_sdir: str, out_dir: str,
                 update_tags: bool) -> Optional[str]:

    external_refs_by_fn = get_wheel_elfdata(wheel_path)[1]
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

                if not soname in soname_map:
                    new_soname, new_path = copylib(src_path, dest_dir)
                    soname_map[soname] = (new_soname, new_path)
                    check_call(['patchelf', '--replace-needed', soname, new_soname, fn])
                # dependency library has already been grafted, so we just need to change soname
                # and add rpath to it in that case
                else:
                    check_call(['patchelf', '--replace-needed', soname, soname_map[soname][0], fn])
                    patchelf_set_rpath(fn, dirname(soname_map[soname][1]))

            if len(ext_libs) > 0:
                patchelf_set_rpath(fn, dest_dir)

        # we grafted in a bunch of libraries and modifed their sonames, but
        # they may have internal dependencies (DT_NEEDED) on one another, so
        # we need to update those records so each now knows about the new
        # name of the other but also its location by adding rpath.
        for old_soname, (new_soname, path) in soname_map.items():
            needed = elf_read_dt_needed(path)
            for n in needed:
                if n in soname_map:
                    check_call(['patchelf', '--replace-needed', n, soname_map[n][0], path])
                    patchelf_set_rpath(path, dirname(soname_map[n][1]))

        if update_tags:
            ctx.out_wheel = add_platforms(ctx, [abi],
                                          get_replace_platforms(abi))
    return ctx.out_wheel


def copylib(src_path, dest_dir):
    """Graft a shared library from the system into the wheel and update the relevant links.

    1) Copy the file from src_path to dest_dir/
    2) Rename the shared object from soname to soname.<unique>
    3) If the library has a RUNPATH/RPATH, update that to point to its new location.
    """
    # Copy the a shared library from the system (src_path) into the wheel
    # if the library has a RUNPATH/RPATH to it's current location on the
    # system, we also update that to point to its new location.

    with open(src_path, 'rb') as f:
        shorthash = hashfile(f)[:8]

    base, ext = os.path.basename(src_path).split('.', 1)
    if not base.endswith('-%s' % shorthash):
        new_soname = '%s-%s.%s' % (base, shorthash, ext)
    else:
        new_soname = src_name

    dest_path = os.path.join(dest_dir, new_soname)
    if os.path.exists(dest_path):
        return new_soname, dest_path

    print('Grafting: %s -> %s' % (src_path, dest_path))
    rpaths = elf_read_rpaths(src_path)
    shutil.copy2(src_path, dest_path)

    verify_patchelf()
    check_call(['patchelf', '--set-soname', new_soname, dest_path])

    for rp in itertools.chain(rpaths['rpaths'], rpaths['runpaths']):
        if is_subdir(rp, os.path.dirname(src_path)):
            patchelf_set_rpath(dest_path, pjoin(
                dirname(dest_path), relpath(rp, dirname(src_path))))
            break

    return new_soname, dest_path


def patchelf_set_rpath(fn, libdir):
    new_rpath = pjoin('$ORIGIN', relpath(libdir, dirname(fn)))
    # Get current rpaths list of the library
    current_rpaths = set(map(lambda rp: pjoin('$ORIGIN', relpath(rp, dirname(fn))), 
                         elf_read_rpaths(fn)['rpaths']))
    # Build a set of equivalent rpaths from the one to add
    new_rpath_set = set([new_rpath])
    if new_rpath.endswith('/'):
        new_rpath_set.add(new_rpath[:-1])
    elif new_rpath.endswith('/.'):
        new_rpath_set.add(new_rpath[:-2])
    else:
        new_rpath_set.add(new_rpath+'/')
        new_rpath_set.add(new_rpath+'/.')
    # Check if the rpath to add is not already in the rpaths list before adding it
    if len(current_rpaths.intersection(new_rpath_set)) == 0:
        # Don't override previously set rpaths
        if current_rpaths:
            rpaths = new_rpath + ':' + ':'.join(current_rpaths)	
        else:
            rpaths = new_rpath
        print('Setting RPATH: %s to "%s"' % (fn, rpaths))
        check_call(['patchelf', '--force-rpath', '--set-rpath', rpaths, fn])
