from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .error import InvalidLibc

logger = logging.getLogger(__name__)


@dataclass(frozen=True, order=True)
class LibcVersion:
    major: int
    minor: int


class Libc(Enum):
    value: str

    GLIBC = "glibc"
    MUSL = "musl"

    def __str__(self) -> str:
        return self.value

    def get_current_version(self) -> LibcVersion:
        if self == Libc.MUSL:
            return _get_musl_version(_find_musl_libc())
        return _get_glibc_version()

    @staticmethod
    def detect() -> Libc:
        # check musl first, default to GLIBC
        try:
            _find_musl_libc()
            logger.debug("Detected musl libc")
            return Libc.MUSL
        except InvalidLibc:
            logger.debug("Falling back to GNU libc")
            return Libc.GLIBC


def _find_musl_libc() -> Path:
    try:
        (dl_path,) = list(Path("/lib").glob("libc.musl-*.so.1"))
    except ValueError:
        msg = "musl libc not detected"
        logger.debug("%s", msg)
        raise InvalidLibc(msg) from None

    return dl_path


def _get_musl_version(ld_path: Path) -> LibcVersion:
    try:
        ld = subprocess.run(
            [ld_path], check=False, errors="strict", stderr=subprocess.PIPE
        ).stderr
    except FileNotFoundError as err:
        msg = "failed to determine musl version"
        logger.exception("%s", msg)
        raise InvalidLibc(msg) from err

    match = re.search(r"Version (?P<major>\d+).(?P<minor>\d+).(?P<patch>\d+)", ld)
    if not match:
        msg = f"failed to parse musl version from string {ld!r}"
        raise InvalidLibc(msg) from None

    return LibcVersion(int(match.group("major")), int(match.group("minor")))


def _get_glibc_version() -> LibcVersion:
    # CS_GNU_LIBC_VERSION is only for glibc and shall return e.g. "glibc 2.3.4"
    try:
        version_string: str | None = os.confstr("CS_GNU_LIBC_VERSION")
        assert version_string is not None
        _, version = version_string.rsplit()
    except (AssertionError, AttributeError, OSError, ValueError) as err:
        # os.confstr() or CS_GNU_LIBC_VERSION not available (or a bad value)...
        msg = "failed to determine glibc version"
        raise InvalidLibc(msg) from err

    m = re.match(r"(?P<major>[0-9]+)\.(?P<minor>[0-9]+)", version)
    if not m:
        msg = f"failed to parse glibc version from string {version!r}"
        raise InvalidLibc(msg)

    return LibcVersion(int(m.group("major")), int(m.group("minor")))
