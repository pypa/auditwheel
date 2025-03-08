"""General tools for working with wheels

Tools that aren't specific to delocation
"""

from __future__ import annotations

import csv
import hashlib
import logging
import os
import zlib
from base64 import urlsafe_b64encode
from collections.abc import Generator, Iterable
from datetime import datetime, timezone
from itertools import product
from os.path import splitext
from pathlib import Path
from types import TracebackType

from packaging.utils import parse_wheel_filename

from ._vendor.wheel.pkginfo import read_pkg_info, write_pkg_info
from .tmpdirs import InTemporaryDirectory
from .tools import dir2zip, unique_by_index, walk, zip2dir

logger = logging.getLogger(__name__)


class WheelToolsError(Exception):
    pass


def _dist_info_dir(bdist_dir: Path) -> Path:
    """Get the .dist-info directory from an unpacked wheel

    Parameters
    ----------
    bdist_dir : Path
        Path of unpacked wheel file
    """

    info_dirs = list(bdist_dir.glob("*.dist-info"))
    if len(info_dirs) != 1:
        msg = "Should be exactly one `*.dist_info` directory"
        raise WheelToolsError(msg)
    return info_dirs[0]


def rewrite_record(bdist_dir: Path) -> None:
    """Rewrite RECORD file with hashes for all files in `wheel_sdir`

    Copied from :method:`wheel.bdist_wheel.bdist_wheel.write_record`

    Will also unsign wheel

    Parameters
    ----------
    bdist_dir : Path
        Path of unpacked wheel file
    """
    info_dir = _dist_info_dir(bdist_dir)
    record_path = info_dir / "RECORD"
    record_relpath = record_path.relative_to(bdist_dir)
    # Unsign wheel - because we're invalidating the record hash
    sig_path = info_dir / "RECORD.jws"
    if sig_path.exists():
        sig_path.unlink()

    def files() -> Generator[Path]:
        for dir_, _, files in walk(bdist_dir):
            for file in files:
                yield dir_ / file

    def skip(path: Path) -> bool:
        """Wheel hashes every possible file."""
        return path == record_relpath

    with open(record_path, "w+", newline="", encoding="utf-8") as record_file:
        writer = csv.writer(record_file)
        for path in files():
            relative_path = path.relative_to(bdist_dir)
            if skip(relative_path):
                hash_ = ""
                size = ""
            else:
                data = path.read_bytes()
                digest = hashlib.sha256(data).digest()
                sha256 = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
                hash_ = f"sha256={sha256}"
                size = f"{len(data)}"
            record_path_ = path.relative_to(bdist_dir).as_posix()
            writer.writerow((record_path_, hash_, size))


class InWheel(InTemporaryDirectory):
    """Context manager for doing things inside wheels

    On entering, you'll find yourself in the root tree of the wheel.  If you've
    asked for an output wheel, then on exit we'll rewrite the wheel record and
    pack stuff up for you.
    """

    def __init__(self, in_wheel: Path, out_wheel: Path | None = None) -> None:
        """Initialize in-wheel context manager

        Parameters
        ----------
        in_wheel : Path
            filename of wheel to unpack and work inside
        out_wheel : None or Path:
            filename of wheel to write after exiting.  If None, don't write and
            discard
        """
        self.in_wheel = in_wheel.absolute()
        self.out_wheel = None if out_wheel is None else out_wheel.absolute()
        self.zip_compression_level = zlib.Z_DEFAULT_COMPRESSION
        super().__init__()

    def __enter__(self) -> Path:
        zip2dir(self.in_wheel, self.name)
        return super().__enter__()

    def __exit__(
        self,
        exc: type[BaseException] | None,
        value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.out_wheel is not None:
            rewrite_record(self.name)
            date_time = None
            timestamp = os.environ.get("SOURCE_DATE_EPOCH")
            if timestamp:
                date_time = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
            dir2zip(self.name, self.out_wheel, self.zip_compression_level, date_time)
        return super().__exit__(exc, value, tb)


class InWheelCtx(InWheel):
    """Context manager for doing things inside wheels

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

    def __init__(self, in_wheel: Path, out_wheel: Path | None = None) -> None:
        """Init in-wheel context manager returning self from enter

        Parameters
        ----------
        in_wheel : Path
            filename of wheel to unpack and work inside
        out_wheel : None or Path:
            filename of wheel to write after exiting.  If None, don't write and
            discard
        """
        super().__init__(in_wheel, out_wheel)
        self.path: Path | None = None

    def __enter__(self):  # type: ignore[no-untyped-def]
        self.path = super().__enter__()
        return self

    def iter_files(self) -> Generator[Path]:
        if self.path is None:
            msg = "This function should be called from context manager"
            raise ValueError(msg)
        record_names = list(self.path.glob("*.dist-info/RECORD"))
        if len(record_names) != 1:
            msg = "Should be exactly one `*.dist_info` directory"
            raise ValueError(msg)

        record = record_names[0].read_text()
        reader = csv.reader(r for r in record.splitlines())
        for row in reader:
            filename = row[0]
            yield Path(filename)


def add_platforms(
    wheel_ctx: InWheelCtx, platforms: list[str], remove_platforms: Iterable[str] = ()
) -> Path:
    """Add platform tags `platforms` to a wheel

    Add any platform tags in `platforms` that are missing
    to wheel_ctx's filename and ``WHEEL`` file.

    Parameters
    ----------
    wheel_ctx : InWheelCtx
        An open wheel context
    platforms : list
        platform tags to add to wheel filename and WHEEL tags - e.g.
        ``('macosx_10_9_intel', 'macosx_10_9_x86_64')
    remove_platforms : iterable
        platform tags to remove to the wheel filename and WHEEL tags, e.g.
        ``('linux_x86_64',)`` when ``('manylinux_x86_64')`` is added
    """
    if wheel_ctx.path is None:
        msg = "This function should be called from wheel_ctx context manager"
        raise ValueError(msg)

    to_remove = list(remove_platforms)  # we might want to modify this, make a copy
    definitely_not_purelib = False

    info_fname = _dist_info_dir(wheel_ctx.path) / "WHEEL"
    info = read_pkg_info(info_fname)
    # Check what tags we have
    if wheel_ctx.out_wheel is not None:
        out_dir = wheel_ctx.out_wheel.parent
        wheel_fname = wheel_ctx.out_wheel.name
    else:
        out_dir = Path.cwd()
        wheel_fname = wheel_ctx.in_wheel.name

    _, _, _, in_tags = parse_wheel_filename(wheel_fname)
    original_fname_tags = sorted({tag.platform for tag in in_tags})
    logger.info("Previous filename tags: %s", ", ".join(original_fname_tags))
    fname_tags = [tag for tag in original_fname_tags if tag not in to_remove]
    fname_tags = unique_by_index(fname_tags + platforms)

    # Can't be 'any' and another platform
    if "any" in fname_tags and len(fname_tags) > 1:
        fname_tags.remove("any")
        to_remove.append("any")
        definitely_not_purelib = True

    if fname_tags != original_fname_tags:
        logger.info("New filename tags: %s", ", ".join(fname_tags))
    else:
        logger.info("No filename tags change needed.")

    fparts = {
        "prefix": wheel_fname.rsplit("-", maxsplit=1)[0],
        "plat": ".".join(fname_tags),
        "ext": splitext(wheel_fname)[1],
    }
    out_wheel_fname = "{prefix}-{plat}{ext}".format(**fparts)
    out_wheel = out_dir / out_wheel_fname

    in_info_tags = [tag for name, tag in info.items() if name == "Tag"]
    logger.info("Previous WHEEL info tags: %s", ", ".join(in_info_tags))
    # Python version, C-API version combinations
    pyc_apis = ["-".join(tag.split("-")[:2]) for tag in in_info_tags]
    # unique Python version, C-API version combinations
    pyc_apis = unique_by_index(pyc_apis)
    # Add new platform tags for each Python version, C-API combination
    wanted_tags = ["-".join(tup) for tup in product(pyc_apis, platforms)]
    new_tags = [tag for tag in wanted_tags if tag not in in_info_tags]
    unwanted_tags = ["-".join(tup) for tup in product(pyc_apis, to_remove)]
    updated_tags = [tag for tag in in_info_tags if tag not in unwanted_tags]
    updated_tags += new_tags
    if updated_tags != in_info_tags:
        del info["Tag"]
        for tag in updated_tags:
            info.add_header("Tag", tag)

        if definitely_not_purelib:
            info["Root-Is-Purelib"] = "False"
            logger.info("Changed wheel type to Platlib")

        logger.info("New WHEEL info tags: %s", ", ".join(info.get_all("Tag")))
        write_pkg_info(info_fname, info)
    else:
        logger.info("No WHEEL info change needed.")
    return out_wheel
