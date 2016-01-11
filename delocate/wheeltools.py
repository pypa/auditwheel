""" General tools for working with wheels

Tools that aren't specific to delocation
"""

import os
from os.path import (join as pjoin, abspath, relpath, exists, sep as psep,
                     splitext, basename, dirname)
import glob
import hashlib
import csv
from itertools import product

from wheel.util import urlsafe_b64encode, open_for_csv, native
from wheel.pkginfo import read_pkg_info, write_pkg_info
from wheel.install import WheelFile

from .tmpdirs import InTemporaryDirectory
from .tools import unique_by_index, zip2dir, dir2zip

class WheelToolsError(Exception):
    pass


def rewrite_record(bdist_dir):
    """ Rewrite RECORD file with hashes for all files in `wheel_sdir`

    Copied from :method:`wheel.bdist_wheel.bdist_wheel.write_record`

    Will also unsign wheel

    Parameters
    ----------
    bdist_dir : str
        Path of unpacked wheel file
    """
    info_dirs = glob.glob(pjoin(bdist_dir, '*.dist-info'))
    if len(info_dirs) != 1:
        raise WheelToolsError("Should be exactly one `*.dist_info` directory")
    record_path = pjoin(info_dirs[0], 'RECORD')
    record_relpath = relpath(record_path, bdist_dir)
    # Unsign wheel - because we're invalidating the record hash
    sig_path = pjoin(info_dirs[0], 'RECORD.jws')
    if exists(sig_path):
        os.unlink(sig_path)

    def walk():
        for dir, dirs, files in os.walk(bdist_dir):
            for f in files:
                yield pjoin(dir, f)

    def skip(path):
        """Wheel hashes every possible file."""
        return (path == record_relpath)

    with open_for_csv(record_path, 'w+') as record_file:
        writer = csv.writer(record_file)
        for path in walk():
            relative_path = relpath(path, bdist_dir)
            if skip(relative_path):
                hash = ''
                size = ''
            else:
                with open(path, 'rb') as f:
                    data = f.read()
                digest = hashlib.sha256(data).digest()
                hash = 'sha256=' + native(urlsafe_b64encode(digest))
                size = len(data)
            record_path = relpath(
                path, bdist_dir).replace(psep, '/')
            writer.writerow((record_path, hash, size))


class InWheel(InTemporaryDirectory):
    """ Context manager for doing things inside wheels

    On entering, you'll find yourself in the root tree of the wheel.  If you've
    asked for an output wheel, then on exit we'll rewrite the wheel record and
    pack stuff up for you.
    """
    def __init__(self, in_wheel, out_wheel=None, ret_self=False):
        """ Initialize in-wheel context manager

        Parameters
        ----------
        in_wheel : str
            filename of wheel to unpack and work inside
        out_wheel : None or str:
            filename of wheel to write after exiting.  If None, don't write and
            discard
        ret_self : bool, optional
            If True, return ``self`` from ``__enter__``, otherwise return the
            directory path.
        """
        self.in_wheel = abspath(in_wheel)
        self.out_wheel = None if out_wheel is None else abspath(out_wheel)
        super(InWheel, self).__init__()

    def __enter__(self):
        zip2dir(self.in_wheel, self.name)
        return super(InWheel, self).__enter__()

    def __exit__(self, exc, value, tb):
        if not self.out_wheel is None:
            rewrite_record(self.name)
            dir2zip(self.name, self.out_wheel)
        return super(InWheel, self).__exit__(exc, value, tb)


class InWheelCtx(InWheel):
    """ Context manager for doing things inside wheels

    On entering, you'll find yourself in the root tree of the wheel.  If you've
    asked for an output wheel, then on exit we'll rewrite the wheel record and
    pack stuff up for you.

    The context manager returns itself from the __enter__ method, so you can
    set things like ``out_wheel``.  This is useful when processing in the wheel
    will dicate what the output wheel name is, or whether you want to save at
    all.

    The current path of the wheel contents is set in the attribute
    ``wheel_path``.
    """
    def __init__(self, in_wheel, out_wheel=None):
        """ Init in-wheel context manager returning self from enter

        Parameters
        ----------
        in_wheel : str
            filename of wheel to unpack and work inside
        out_wheel : None or str:
            filename of wheel to write after exiting.  If None, don't write and
            discard
        """
        super(InWheelCtx, self).__init__(in_wheel, out_wheel)
        self.wheel_path = None

    def __enter__(self):
        self.wheel_path = super(InWheelCtx, self).__enter__()
        return self


def add_platforms(in_wheel, platforms, out_path=None, clobber=False):
    """ Add platform tags `platforms` to `in_wheel` filename and WHEEL tags

    Add any platform tags in `platforms` that are missing from `in_wheel`
    filename.

    Add any platform tags in `platforms` that are missing from `in_wheel`
    ``WHEEL`` file.

    Parameters
    ----------
    in_wheel : str
        Filename of wheel to which to add platform tags
    platforms : iterable
        platform tags to add to wheel filename and WHEEL tags - e.g.
        ``('macosx_10_9_intel', 'macosx_10_9_x86_64')
    out_path : None or str, optional
        Directory to which to write new wheel.  Default is directory containing
        `in_wheel`
    clobber : bool, optional
        If True, overwrite existing output filename, otherwise raise error

    Returns
    -------
    out_wheel : None or str
        Absolute path of wheel file written, or None if no wheel file written.
    """
    in_wheel = abspath(in_wheel)
    out_path = dirname(in_wheel) if out_path is None else abspath(out_path)
    wf = WheelFile(in_wheel)
    info_fname = wf.wheelinfo_name
    # Check what tags we have
    in_fname_tags = wf.parsed_filename.groupdict()['plat'].split('.')
    extra_fname_tags = [tag for tag in platforms if tag not in in_fname_tags]
    in_wheel_base, ext = splitext(basename(in_wheel))
    out_wheel_base = '.'.join([in_wheel_base] + list(extra_fname_tags))
    out_wheel = pjoin(out_path, out_wheel_base + ext)
    if exists(out_wheel) and not clobber:
        raise WheelToolsError('Not overwriting {0}; set clobber=True '
                              'to overwrite'.format(out_wheel))
    with InWheelCtx(in_wheel) as ctx:
        info = read_pkg_info(info_fname)
        if info['Root-Is-Purelib'] == 'true':
            raise WheelToolsError('Cannot add platforms to pure wheel')
        in_info_tags = [tag for name, tag in info.items() if name == 'Tag']
        # Python version, C-API version combinations
        pyc_apis = ['-'.join(tag.split('-')[:2]) for tag in in_info_tags]
        # unique Python version, C-API version combinations
        pyc_apis = unique_by_index(pyc_apis)
        # Add new platform tags for each Python version, C-API combination
        required_tags = ['-'.join(tup) for tup in product(pyc_apis, platforms)]
        needs_write = False
        for req_tag in required_tags:
            if req_tag in in_info_tags: continue
            needs_write = True
            info.add_header('Tag', req_tag)
        if needs_write:
            write_pkg_info(info_fname, info)
            # Tell context manager to write wheel on exit by setting filename
            ctx.out_wheel = out_wheel
    return ctx.out_wheel
