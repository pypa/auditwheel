""" Tools for getting and setting install names """

from subprocess import Popen, PIPE

import os
from os.path import join as pjoin, relpath, isdir, exists
import zipfile
import re
import stat

class InstallNameError(Exception):
    pass


def back_tick(cmd, ret_err=False, as_str=True, raise_err=None):
    """ Run command `cmd`, return stdout, or stdout, stderr if `ret_err`

    Roughly equivalent to ``check_output`` in Python 2.7

    Parameters
    ----------
    cmd : sequence
        command to execute
    ret_err : bool, optional
        If True, return stderr in addition to stdout.  If False, just return
        stdout
    as_str : bool, optional
        Whether to decode outputs to unicode string on exit.
    raise_err : None or bool, optional
        If True, raise RuntimeError for non-zero return code. If None, set to
        True when `ret_err` is False, False if `ret_err` is True

    Returns
    -------
    out : str or tuple
        If `ret_err` is False, return stripped string containing stdout from
        `cmd`.  If `ret_err` is True, return tuple of (stdout, stderr) where
        ``stdout`` is the stripped stdout, and ``stderr`` is the stripped
        stderr.

    Raises
    ------
    Raises RuntimeError if command returns non-zero exit code and `raise_err`
    is True
    """
    if raise_err is None:
        raise_err = False if ret_err else True
    cmd_is_seq = isinstance(cmd, (list, tuple))
    proc = Popen(cmd, stdout=PIPE, stderr=PIPE, shell=not cmd_is_seq)
    out, err = proc.communicate()
    retcode = proc.returncode
    cmd_str = ' '.join(cmd) if cmd_is_seq else cmd
    if retcode is None:
        proc.terminate()
        raise RuntimeError(cmd_str + ' process did not terminate')
    if raise_err and retcode != 0:
        raise RuntimeError('{0} returned code {1} with error {2}'.format(
                           cmd_str, retcode, err.decode('latin-1')))
    out = out.strip()
    if as_str:
        out = out.decode('latin-1')
    if not ret_err:
        return out
    err = err.strip()
    if as_str:
        err = err.decode('latin-1')
    return out, err


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


def ensure_writable(f):
    """decorator to ensure a filename is writable before modifying it

    If changed, original permissions are restored after the decorated modification.
    """
    def modify(filename, *args, **kwargs):
        m = os.stat(filename).st_mode
        if not m & stat.S_IWUSR:
            os.chmod(filename, m | stat.S_IWUSR)
        try:
            return f(filename, *args, **kwargs)
        finally:
            # restore original permissions
            if not m & stat.S_IWUSR:
                os.chmod(filename, m)

    return modify


IN_RE = re.compile("(.*) \(compatibility version (\d+\.\d+\.\d+), "
                   "current version (\d+\.\d+\.\d+)\)")

def parse_install_name(line):
    """ Parse a line of install name output

    Parameters
    ----------
    line : str
        line of install name output from ``otool``

    Returns
    -------
    libname : str
        library install name
    compat_version : str
        compatibility version
    current_version : str
        current version
    """
    line = line.strip()
    return IN_RE.match(line).groups()


def _line0_says_object(line0, filename):
    line0 = line0.strip()
    if line0.startswith('Archive :'):
        # nothing to do for static libs
        return False
    if not line0.startswith(filename + ':'):
        raise InstallNameError('Unexpected first line: ' + line0)
    further_report = line0[len(filename) + 1:]
    if further_report == '':
        return True
    if further_report == ' is not an object file':
        return False
    raise InstallNameError(
        'Too ignorant to know what "{0}" means'.format(further_report))


def get_install_names(filename):
    """ Return install names from library named in `filename`

    Returns tuple of install names

    tuple will be empty if no install names, or if this is not an object file.

    Parameters
    ----------
    filename : str
        filename of library

    Returns
    -------
    install_names : tuple
        tuple of install names for library `filename`
    """
    out = back_tick(['otool', '-L', filename])
    lines = out.split('\n')
    if not _line0_says_object(lines[0], filename):
        return ()
    names = tuple(parse_install_name(line)[0] for line in lines[1:])
    install_id = get_install_id(filename)
    if not install_id is None:
        assert names[0] == install_id
        return names[1:]
    return names


def get_install_id(filename):
    """ Return install id from library named in `filename`

    Returns None if no install id, or if this is not an object file.

    Parameters
    ----------
    filename : str
        filename of library

    Returns
    -------
    install_id : str
        install id of library `filename`, or None if no install id
    """
    out = back_tick(['otool', '-D', filename])
    lines = out.split('\n')
    if not _line0_says_object(lines[0], filename):
        return None
    if len(lines) == 1:
        return None
    if len(lines) != 2:
        raise InstallNameError('Unexpected otool output ' + out)
    return lines[1].strip()


@ensure_writable
def set_install_name(filename, oldname, newname):
    """ Set install name `oldname` to `newname` in library filename

    Parameters
    ----------
    filename : str
        filename of library
    oldname : str
        current install name in library
    newname : str
        replacement name for `oldname`
    """
    names = get_install_names(filename)
    if oldname not in names:
        raise InstallNameError('{0} not in install names for {1}'.format(
            oldname, filename))
    back_tick(['install_name_tool', '-change', oldname, newname, filename])


@ensure_writable
def set_install_id(filename, install_id):
    """ Set install id for library named in `filename`

    Parameters
    ----------
    filename : str
        filename of library
    install_id : str
        install id for library `filename`

    Raises
    ------
    RuntimeError if `filename` has not install id
    """
    if get_install_id(filename) is None:
        raise InstallNameError('{0} has no install id'.format(filename))
    back_tick(['install_name_tool', '-id', install_id, filename])


RPATH_RE = re.compile("path (.*) \(offset \d+\)")

def get_rpaths(filename):
    """ Return rpaths from library `filename`

    Parameters
    ----------
    filaname : str
        filename of library

    Returns
    -------
    rpath : tuple
        rpath paths in `filename`
    """
    out = back_tick(['otool', '-l', filename])
    lines = [line.strip() for line in out.split('\n')]
    assert lines[0] == filename + ':'
    paths = []
    line_no = 1
    while line_no < len(lines):
        line = lines[line_no]
        line_no += 1
        if line != 'cmd LC_RPATH':
            continue
        cmdsize, path = lines[line_no:line_no+2]
        assert cmdsize.startswith('cmdsize ')
        paths.append(RPATH_RE.match(path).groups()[0])
        line_no += 2
    return tuple(paths)


@ensure_writable
def add_rpath(filename, newpath):
    """ Add rpath `newpath` to library `filename`

    Parameters
    ----------
    filename : str
        filename of library
    newpath : str
        rpath to add
    """
    back_tick(['install_name_tool', '-add_rpath', newpath, filename])


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
    back_tick(['unzip', '-o', '-d', out_dir, zip_fname])


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
    z = zipfile.ZipFile(zip_fname, 'w',
                        compression=zipfile.ZIP_DEFLATED)
    for root, dirs, files in os.walk(in_dir):
        for file in files:
            fname = pjoin(root, file)
            out_fname = relpath(fname, in_dir)
            z.write(os.path.join(root, file), out_fname)
    z.close()


def find_package_dirs(root_path):
    """ Find python package directories in directory `root_path`

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


def cmp_contents(filename1, filename2):
    """ Returns True if contents of the files are the same

    Parameters
    ----------
    filename1 : str
        filename of first file to compare
    filename2 : str
        filename of second file to compare

    Returns
    -------
    tf : bool
        True if binary contents of `filename1` is same as binary contents of
        `filename2`, False otherwise.
    """
    with open(filename1, 'rb') as fobj:
        contents1 = fobj.read()
    with open(filename2, 'rb') as fobj:
        contents2 = fobj.read()
    return contents1 == contents2


def get_archs(libname):
    """ Return architecture types from library `libname`

    Parameters
    ----------
    libname : str
        filename of binary for which to return arch codes

    Returns
    -------
    arch_names : frozenset
        Empty (frozen)set if no arch codes.  If not empty, contains one or more
        of 'ppc', 'ppc64', 'i386', 'x86_64'
    """
    if not exists(libname):
        raise RuntimeError(libname + " is not a file")
    try:
        stdout = back_tick(['lipo', '-info', libname])
    except RuntimeError:
        return frozenset()
    lines = [line.strip() for line in stdout.split('\n') if line.strip()]
    # For some reason, output from lipo -info on .a file generates this line
    if lines[0] == "input file {0} is not a fat file".format(libname):
        line = lines[1]
    else:
        assert len(lines) == 1
        line = lines[0]
    for reggie in (
        'Non-fat file: {0} is architecture: (.*)'.format(libname),
        'Architectures in the fat file: {0} are: (.*)'.format(libname)):
        reggie = re.compile(reggie)
        match = reggie.match(line)
        if not match is None:
            return frozenset(match.groups()[0].split(' '))
    raise ValueError("Unexpected output: '{0}' for {1}".format(
        stdout, libname))


def lipo_fuse(in_fname1, in_fname2, out_fname):
    """ Use lipo to merge libs `filename1`, `filename2`, store in `out_fname`

    Parameters
    ----------
    in_fname1 : str
        filename of library
    in_fname2 : str
        filename of library
    out_fname : str
        filename to which to write new fused library
    """
    return back_tick(['lipo', '-create',
                      in_fname1, in_fname2,
                      '-output', out_fname])
