import os
import shutil
from glob import glob
from os.path import exists, isfile, isdir
from os.path import join as pjoin
import zipfile
import subprocess


def unique_by_index(sequence):
    """ unique elements in `sequence` in the order in which they occur

    Parameters
    ----------
    sequence : iterable

    Returns
    -------
    uniques : list
        unique elements of sequence, ordered by the order in which the element
        occurs in `sequence`
    """
    uniques = []
    for element in sequence:
        if element not in uniques:
            uniques.append(element)
    return uniques


def zip2dir(zip_fname, out_dir):
    """ Extract `zip_fname` into output directory `out_dir`

    Parameters
    ----------
    zip_fname : str
        Filename of zip archive to write
    out_dir : str
        Directory path containing files to go in the zip archive
    """
    # Use unzip command rather than zipfile module to preserve permissions
    # http://bugs.python.org/issue15795
    subprocess.check_output(['unzip', '-o', '-d', out_dir, zip_fname])

    try:
        # but sometimes preserving permssions is really bad, and makes it
        # we don't have the permissions to read any of the files
        with open(glob(pjoin(out_dir, '*.dist-info/RECORD'))[0]) as f:
            pass
    except PermissionError:
        shutil.rmtree(out_dir)
        with zipfile.ZipFile(zip_fname) as zf:
            zf.extractall(out_dir)


def dir2zip(in_dir, zip_fname):
    """ Make a zip file `zip_fname` with contents of directory `in_dir`

    The recorded filenames are relative to `in_dir`, so doing a standard zip
    unpack of the resulting `zip_fname` in an empty directory will result in
    the original directory contents.

    Parameters
    ----------
    in_dir : str
        Directory path containing files to go in the zip archive
    zip_fname : str
        Filename of zip archive to write
    """
    z = zipfile.ZipFile(zip_fname, 'w', compression=zipfile.ZIP_DEFLATED)
    for root, dirs, files in os.walk(in_dir):
        for file in files:
            fname = os.path.join(root, file)
            out_fname = os.path.relpath(fname, in_dir)
            z.write(os.path.join(root, file), out_fname)
    z.close()


def tarbz2todir(tarbz2_fname, out_dir):
    """Extract `tarbz2_fname` into output directory `out_dir`
    """
    subprocess.check_output(['tar', 'xjf', tarbz2_fname, '-C', out_dir])


def find_package_dirs(root_path):
    """Find python package directories in directory `root_path`

    Parameters
    ----------
    root_path : str
        Directory to search for package subdirectories

    Returns
    -------
    package_sdirs : set
        Set of strings where each is a subdirectory of `root_path`, containing
        an ``__init__.py`` file.  Paths prefixed by `root_path`
    """
    package_sdirs = set()
    for entry in os.listdir(root_path):
        fname = entry if root_path == '.' else pjoin(root_path, entry)
        if isdir(fname) and exists(pjoin(fname, '__init__.py')):
            package_sdirs.add(fname)
    return package_sdirs
