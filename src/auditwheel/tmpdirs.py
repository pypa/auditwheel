"""Contexts for *with* statement providing temporary directories"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import TracebackType


class InTemporaryDirectory:
    """Create, return, and change directory to a temporary directory

    Examples
    --------
    >>> from pathlib import Path
    >>> my_cwd = Path.cwd()
    >>> with InTemporaryDirectory() as tmpdir:
    ...     _ = open('test.txt', 'wt').write('some text')
    ...     assert os.path.isfile('test.txt')
    ...     assert tmpdir.joinpath('test.txt').is_file()
    >>> tmpdir.exists()
    False
    >>> Path.cwd() == my_cwd
    True
    """

    def __init__(self) -> None:
        self._tmpdir = TemporaryDirectory()
        self._name = Path(self._tmpdir.name).resolve(strict=True)

    @property
    def name(self) -> Path:
        return self._name

    def __enter__(self) -> Path:
        self._pwd = Path.cwd()
        os.chdir(self._name)
        self._tmpdir.__enter__()
        return self._name

    def __exit__(
        self,
        exc: type[BaseException] | None,
        value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        os.chdir(self._pwd)
        self._tmpdir.__exit__(exc, value, tb)


class InGivenDirectory:
    """Change directory to given directory for duration of ``with`` block

    Useful when you want to use `InTemporaryDirectory` for the final test, but
    you are still debugging.  For example, you may want to do this in the end:

    >>> with InTemporaryDirectory() as tmpdir:
    ...     # do something complicated which might break
    ...     pass

    But indeed the complicated thing does break, and meanwhile the
    ``InTemporaryDirectory`` context manager wiped out the directory with the
    temporary files that you wanted for debugging.  So, while debugging, you
    replace with something like:

    >>> with InGivenDirectory() as tmpdir: # Use working directory by default
    ...     # do something complicated which might break
    ...     pass

    You can then look at the temporary file outputs to debug what is happening,
    fix, and finally replace ``InGivenDirectory`` with ``InTemporaryDirectory``
    again.
    """

    def __init__(self, path: Path | None = None) -> None:
        """Initialize directory context manager

        Parameters
        ----------
        path : None or Path, optional
            path to change directory to, for duration of ``with`` block.
            Defaults to ``Path.cwd()`` if None
        """
        if path is None:
            path = Path.cwd()
        self.name = path.absolute()

    def __enter__(self) -> Path:
        self._pwd = Path.cwd()
        if not self.name.is_dir():
            self.name.mkdir()
        os.chdir(self.name)
        return self.name

    def __exit__(
        self,
        exc: type[BaseException] | None,
        value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        os.chdir(self._pwd)
