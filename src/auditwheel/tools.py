from __future__ import annotations

import argparse
import logging
import os
import subprocess
import zipfile
import zlib
from collections.abc import Generator, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

_T = TypeVar("_T")

logger = logging.getLogger(__name__)

# Default: zlib.Z_DEFAULT_COMPRESSION (-1 aka. level 6) balances speed and size.
# Maintained for typical builds where iteration speed outweighs distribution savings.
# Override via AUDITWHEEL_ZIP_LEVEL/--zip-level for:
# - some test builds that needs no compression at all (0)
# - bandwidth-constrained or large amount of downloads (9)
_COMPRESS_LEVEL = zlib.Z_DEFAULT_COMPRESSION


def unique_by_index(sequence: Iterable[_T]) -> list[_T]:
    """unique elements in `sequence` in the order in which they occur

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


def walk(topdir: Path) -> Generator[tuple[Path, list[str], list[str]]]:
    """Wrapper for `os.walk` with outputs in reproducible order

    Parameters
    ----------
    topdir : Path
        Root of the directory tree

    Yields
    ------
    dirpath : Path
        Path to a directory
    dirnames : list[str]
        List of subdirectory names in `dirpath`
    filenames : list[str]
        List of non-directory file names in `dirpath`
    """
    topdir = topdir.resolve(strict=True)
    for dirpath_, dirnames, filenames in os.walk(topdir):
        dirpath = Path(dirpath_)
        # sort list of dirnames in-place such that `os.walk`
        # will recurse into subdirectories in reproducible order
        dirnames.sort()
        # recurse into any top-level .dist-info subdirectory last
        if dirpath == topdir:
            subdirs = []
            dist_info = []
            for dir in dirnames:
                if dir.endswith(".dist-info"):
                    dist_info.append(dir)
                else:
                    subdirs.append(dir)
            dirnames[:] = subdirs
            dirnames.extend(dist_info)
            del dist_info
        # sort list of filenames for iteration in reproducible order
        filenames.sort()
        # list any dist-info/RECORD file last
        if (
            dirpath.name.endswith(".dist-info")
            and dirpath.parent == topdir
            and "RECORD" in filenames
        ):
            filenames.remove("RECORD")
            filenames.append("RECORD")
        yield dirpath, dirnames, filenames


def zip2dir(zip_fname: Path, out_dir: Path) -> None:
    """Extract `zip_fname` into output directory `out_dir`

    Parameters
    ----------
    zip_fname : str
        Filename of zip archive to write
    out_dir : str
        Directory path containing files to go in the zip archive
    """
    start = datetime.now()
    with zipfile.ZipFile(zip_fname, "r") as z:
        for name in z.namelist():
            member = z.getinfo(name)
            extracted_path = z.extract(member, out_dir)
            attr = member.external_attr >> 16
            if member.is_dir():
                # this is always rebuilt as 755 by dir2zip
                os.chmod(extracted_path, 0o755)
            elif attr != 0:
                attr &= 511  # only keep permission bits
                attr |= 6 << 6  # at least read/write for current user
                os.chmod(extracted_path, attr)
    logger.debug(
        "zip2dir from %s to %s takes %s", zip_fname, out_dir, datetime.now() - start
    )


def dir2zip(in_dir: Path, zip_fname: Path, date_time: datetime | None = None) -> None:
    """Make a zip file `zip_fname` with contents of directory `in_dir`

    The recorded filenames are relative to `in_dir`, so doing a standard zip
    unpack of the resulting `zip_fname` in an empty directory will result in
    the original directory contents.

    Parameters
    ----------
    in_dir : Path
        Directory path containing files to go in the zip archive
    zip_fname : Path
        Filename of zip archive to write
    date_time : Optional[datetime]
        Time stamp to set on each file in the archive
    """
    start = datetime.now()
    in_dir = in_dir.resolve(strict=True)
    if date_time is None:
        st = in_dir.stat()
        date_time = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
    date_time_args = date_time.timetuple()[:6]
    compression = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(zip_fname, "w", compression=compression) as z:
        for dname, _, files in walk(in_dir):
            if dname != in_dir:
                out_dname = f"{dname.relative_to(in_dir)}/"
                zinfo = zipfile.ZipInfo.from_file(dname, out_dname)
                zinfo.date_time = date_time_args
                z.writestr(zinfo, b"")
            for file in files:
                fname = dname / file
                out_fname = fname.relative_to(in_dir)
                zinfo = zipfile.ZipInfo.from_file(fname, out_fname)
                zinfo.date_time = date_time_args
                zinfo.compress_type = compression
                with open(fname, "rb") as fp:
                    z.writestr(zinfo, fp.read(), compresslevel=_COMPRESS_LEVEL)
    logger.debug(
        "dir2zip from %s to %s takes %s", in_dir, zip_fname, datetime.now() - start
    )


def tarbz2todir(tarbz2_fname: Path, out_dir: Path) -> None:
    """Extract `tarbz2_fname` into output directory `out_dir`"""
    subprocess.check_output(["tar", "xjf", tarbz2_fname, "-C", out_dir])


class EnvironmentDefault(argparse.Action):
    """Get values from environment variable."""

    def __init__(
        self,
        env: str,
        required: bool = True,
        default: str | None = None,
        choices: Iterable[str] | None = None,
        type: type | None = None,
        **kwargs: Any,
    ) -> None:
        self.env_default = os.environ.get(env)
        self.env = env
        if self.env_default:
            if type:
                try:
                    self.env_default = type(self.env_default)
                except Exception:
                    self.option_strings = kwargs["option_strings"]
                    args = {
                        "value": self.env_default,
                        "type": type,
                        "env": self.env,
                    }
                    msg = (
                        "invalid type: %(value)r from environment variable "
                        "%(env)r cannot be converted to %(type)r"
                    )
                    raise argparse.ArgumentError(self, msg % args) from None
            default = self.env_default
        if (
            self.env_default is not None
            and choices is not None
            and self.env_default not in choices
        ):
            self.option_strings = kwargs["option_strings"]
            args = {
                "value": self.env_default,
                "choices": ", ".join(map(repr, choices)),
                "env": self.env,
            }
            msg = (
                "invalid choice: %(value)r from environment variable "
                "%(env)r (choose from %(choices)s)"
            )
            raise argparse.ArgumentError(self, msg % args)

        if default is not None:
            required = False

        super().__init__(
            default=default, required=required, choices=choices, type=type, **kwargs
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,  # noqa: ARG002
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,  # noqa: ARG002
    ) -> None:
        setattr(namespace, self.dest, values)
