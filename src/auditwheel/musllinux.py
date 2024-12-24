from __future__ import annotations

import logging
import pathlib
import re
from typing import NamedTuple

LOG = logging.getLogger(__name__)
VERSION_RE = re.compile(b"[^.](?P<major>\\d+)\\.(?P<minor>\\d+)\\.(?P<patch>\\d+)\0")


class MuslVersion(NamedTuple):
    major: int
    minor: int
    patch: int


def find_musl_libc(library_path: str | None = None) -> pathlib.Path | None:
    try:
        (dl_path,) = list(pathlib.Path(library_path or "/lib").glob("libc.musl-*.so.1"))
    except ValueError:
        return None

    return dl_path


def get_musl_version(ld_path: pathlib.Path) -> MuslVersion | None:
    try:
        with open(ld_path, "rb") as fp:
            text = fp.read()
    except FileNotFoundError:
        return None

    for match in VERSION_RE.finditer(text):
        return MuslVersion(
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch")),
        )

    LOG.error("Failed to determine musl version", exc_info=True)
    return None
