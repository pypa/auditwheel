from __future__ import annotations

import logging
import pathlib
import re
import subprocess
from typing import NamedTuple

from auditwheel.error import InvalidLibc

LOG = logging.getLogger(__name__)


class MuslVersion(NamedTuple):
    major: int
    minor: int
    patch: int


def find_musl_libc() -> pathlib.Path:
    try:
        (dl_path,) = list(pathlib.Path("/lib").glob("libc.musl-*.so.1"))
    except ValueError:
        LOG.debug("musl libc not detected")
        raise InvalidLibc() from None

    return dl_path


def get_musl_version(ld_path: pathlib.Path) -> MuslVersion:
    try:
        ld = subprocess.run(
            [ld_path], check=False, errors="strict", stderr=subprocess.PIPE
        ).stderr
    except FileNotFoundError as err:
        LOG.exception("Failed to determine musl version")
        raise InvalidLibc() from err

    match = re.search(r"Version (?P<major>\d+).(?P<minor>\d+).(?P<patch>\d+)", ld)
    if not match:
        raise InvalidLibc() from None

    return MuslVersion(
        int(match.group("major")), int(match.group("minor")), int(match.group("patch"))
    )
