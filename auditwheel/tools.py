import argparse
import os
import shutil
from glob import glob
from os.path import join as pjoin
from typing import Any, Iterable, List
import zipfile
import subprocess


def unique_by_index(sequence: Iterable[Any]) -> List[Any]:
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


def zip2dir(zip_fname: str, out_dir: str) -> None:
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
        with open(glob(pjoin(out_dir, '*.dist-info/RECORD'))[0]):
            pass
    except PermissionError:
        shutil.rmtree(out_dir)
        with zipfile.ZipFile(zip_fname) as zf:
            zf.extractall(out_dir)


def dir2zip(in_dir: str, zip_fname: str) -> None:
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
    with zipfile.ZipFile(zip_fname, 'w',
                         compression=zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(in_dir):
            for file in files:
                fname = os.path.join(root, file)
                out_fname = os.path.relpath(fname, in_dir)
                z.write(os.path.join(root, file), out_fname)


def tarbz2todir(tarbz2_fname: str, out_dir: str) -> None:
    """Extract `tarbz2_fname` into output directory `out_dir`
    """
    subprocess.check_output(['tar', 'xjf', tarbz2_fname, '-C', out_dir])


class EnvironmentDefault(argparse.Action):
    """Get values from environment variable."""

    def __init__(self, env, required=True, default=None, **kwargs):
        self.env_default = os.environ.get(env)
        self.env = env
        if self.env_default:
            default = self.env_default
        if default:
            required = False
        if self.env_default and 'choices' in kwargs:
            choices = kwargs['choices']
            if self.env_default not in choices:
                self.option_strings = kwargs['option_strings']
                args = {'value': self.env_default,
                        'choices': ', '.join(map(repr, choices)),
                        'env': self.env}
                msg = 'invalid choice: %(value)r from environment variable '\
                      '%(env)r (choose from %(choices)s)'
                raise argparse.ArgumentError(self, msg % args)

        super().__init__(
            default=default,
            required=required,
            **kwargs
        )

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)
