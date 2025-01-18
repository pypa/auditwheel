from __future__ import annotations

import re
from itertools import chain
from shutil import which
from subprocess import CalledProcessError, check_call, check_output


class ElfPatcher:
    def replace_needed(self, file_name: str, *old_new_pairs: tuple[str, str]) -> None:
        raise NotImplementedError()

    def set_soname(self, file_name: str, new_so_name: str) -> None:
        raise NotImplementedError()

    def set_rpath(self, file_name: str, rpath: str) -> None:
        raise NotImplementedError()

    def get_rpath(self, file_name: str) -> str:
        raise NotImplementedError()


def _verify_patchelf() -> None:
    """This function looks for the ``patchelf`` external binary in the PATH,
    checks for the required version, and throws an exception if a proper
    version can't be found. Otherwise, silence is golden
    """
    if not which("patchelf"):
        msg = "Cannot find required utility `patchelf` in PATH"
        raise ValueError(msg)
    try:
        version = check_output(["patchelf", "--version"]).decode("utf-8")
    except CalledProcessError:
        msg = "Could not call `patchelf` binary"
        raise ValueError(msg) from None

    m = re.match(r"patchelf\s+(\d+(.\d+)?)", version)
    if m and tuple(int(x) for x in m.group(1).split(".")) >= (0, 14):
        return
    msg = f"patchelf {version} found. auditwheel repair requires patchelf >= 0.14."
    raise ValueError(msg)


class Patchelf(ElfPatcher):
    def __init__(self) -> None:
        _verify_patchelf()

    def replace_needed(self, file_name: str, *old_new_pairs: tuple[str, str]) -> None:
        check_call(
            [
                "patchelf",
                *chain.from_iterable(
                    ("--replace-needed", *pair) for pair in old_new_pairs
                ),
                file_name,
            ]
        )

    def set_soname(self, file_name: str, new_so_name: str) -> None:
        check_call(["patchelf", "--set-soname", new_so_name, file_name])

    def set_rpath(self, file_name: str, rpath: str) -> None:
        check_call(["patchelf", "--remove-rpath", file_name])
        check_call(["patchelf", "--force-rpath", "--set-rpath", rpath, file_name])

    def get_rpath(self, file_name: str) -> str:
        return (
            check_output(["patchelf", "--print-rpath", file_name])
            .decode("utf-8")
            .strip()
        )
