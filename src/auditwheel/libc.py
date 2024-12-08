from __future__ import annotations

import logging
from enum import IntEnum

from .musllinux import find_musl_libc

logger = logging.getLogger(__name__)


class Libc(IntEnum):
    GLIBC = (1,)
    MUSL = (2,)


def get_libc() -> Libc:
    if find_musl_libc() is not None:
        logger.debug("Detected musl libc")
        return Libc.MUSL
    return Libc.GLIBC
