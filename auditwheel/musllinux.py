import logging
import pathlib
import subprocess
import re
import sys
from typing import NamedTuple

from auditwheel.error import InvalidPlatform

LOG = logging.getLogger(__name__)


class MuslVersion(NamedTuple):
    major: int
    minor: int
    patch: int


def find_musl_libc() -> pathlib.Path:
    try:
        ldd = subprocess.run(["ldd", "/bin/ls"],
                             text=True,
                             capture_output=True)
    except subprocess.CalledProcessError:
        LOG.error("Failed to determine libc version", exc_info=True)
        raise

    match = re.search(
        r"libc\.musl-(?P<platform>\w+)\.so.1 "  # TODO drop the platform
        r"=> (?P<path>[/\-\w.]+)",
        ldd.stdout)

    if not match:
        raise InvalidPlatform

    return pathlib.Path(match.group("path"))


def get_musl_version(ld_path: pathlib.Path) -> MuslVersion:
    try:
        ld = subprocess.run([ld_path], text=True, capture_output=True)
    except subprocess.CalledProcessError:
        LOG.error("Failed to determine musl version", exc_info=True)
        raise

    match = re.search(
        r"Version "
        r"(?P<major>\d)."
        r"(?P<minor>\d)."
        r"(?P<patch>\d)",
        ld.stderr)
    if not match:
        raise InvalidPlatform

    return MuslVersion(
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")))


if __name__ == "__main__":
    libc_path = find_musl_libc()
    version = get_musl_version(libc_path)
    print(f"Found musl version {version} in {libc_path}")
    wheel_path = pathlib.Path(sys.argv[1])
