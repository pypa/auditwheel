from __future__ import annotations

from pathlib import Path

from .condatools import InCondaPkgCtx
from .wheeltools import InWheelCtx


def InGenericPkgCtx(
    in_path: Path, out_path: Path | None = None
) -> InWheelCtx | InCondaPkgCtx:
    """Factory that returns a InWheelCtx or InCondaPkgCtx
    context manager depending on the file extension
    """
    if in_path.name.endswith(".whl"):
        return InWheelCtx(in_path, out_path)
    if in_path.name.endswith(".tar.bz2"):
        if out_path is not None:
            raise NotImplementedError()
        return InCondaPkgCtx(in_path)
    msg = f"Invalid package: {in_path}. File formats supported: .whl, .tar.bz2"
    raise ValueError(msg)
