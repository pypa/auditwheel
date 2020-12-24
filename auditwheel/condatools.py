"""Context managers like those in wheeltools.py for unpacking
conda packages.
"""
import os

from .tmpdirs import InTemporaryDirectory
from .tools import tarbz2todir


class InCondaPkg(InTemporaryDirectory):
    def __init__(self, in_conda_pkg):
        """Initialize in-conda-package context manager"""
        self.in_conda_pkg = os.path.abspath(in_conda_pkg)
        super().__init__()

    def __enter__(self):
        tarbz2todir(self.in_conda_pkg, self.name)
        return super().__enter__()


class InCondaPkgCtx(InCondaPkg):
    def __init__(self, in_conda_pkg):
        super().__init__(in_conda_pkg)
        self.path = None

    def __enter__(self):
        self.path = super().__enter__()
        return self

    def iter_files(self):
        files = os.path.join(self.path, 'info', 'files')
        with open(files) as f:
            return [line.strip() for line in f.readlines()]
