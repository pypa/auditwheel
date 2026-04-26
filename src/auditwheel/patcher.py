from __future__ import annotations

import re
from itertools import chain
from shutil import which
from subprocess import CalledProcessError, check_call, check_output
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class ElfPatcher:
    def replace_needed(self, file_name: Path, *old_new_pairs: tuple[str, str]) -> None:
        raise NotImplementedError

    def remove_needed(self, file_name: Path, *sonames: str) -> None:
        raise NotImplementedError

    def set_soname(self, file_name: Path, new_so_name: str) -> None:
        raise NotImplementedError

    def set_rpath(self, file_name: Path, rpath: str) -> None:
        raise NotImplementedError

    def get_rpath(self, file_name: Path) -> str:
        raise NotImplementedError


def _verify_patchelf(*, allow_lief: bool) -> str:
    """This function looks for the ``lief-patchelf`` or ``patchelf`` external binary in the PATH,
    checks for the required version, and throws an exception if a proper
    version can't be found. Otherwise, silence is golden
    """
    result = which("lief-patchelf") if allow_lief else None
    if result is None:
        result = which("patchelf")
        if not result:
            msg = "Cannot find required utility `patchelf` in PATH"
            raise ValueError(msg)
        try:
            version = check_output([result, "--version"]).decode("utf-8")
        except CalledProcessError:
            msg = "Could not call `patchelf` binary"
            raise ValueError(msg) from None

        m = re.match(r"patchelf\s+(\d+(.\d+)?)", version)
        if not (m and tuple(int(x) for x in m.group(1).split(".")) >= (0, 14)):
            msg = f"patchelf {version} found. auditwheel repair requires patchelf >= 0.14."
            raise ValueError(msg)

    return result


class Patchelf(ElfPatcher):
    def __init__(self, *, allow_lief: bool = True) -> None:
        self.patchelf_path = _verify_patchelf(allow_lief=allow_lief)

    def replace_needed(self, file_name: Path, *old_new_pairs: tuple[str, str]) -> None:
        check_call(
            [
                self.patchelf_path,
                *chain.from_iterable(("--replace-needed", *pair) for pair in old_new_pairs),
                file_name,
            ],
        )

    def remove_needed(self, file_name: Path, *sonames: str) -> None:
        check_call(
            [
                self.patchelf_path,
                *chain.from_iterable(("--remove-needed", soname) for soname in sonames),
                file_name,
            ],
        )

    def set_soname(self, file_name: Path, new_so_name: str) -> None:
        check_call([self.patchelf_path, "--set-soname", new_so_name, file_name])

    def set_rpath(self, file_name: Path, rpath: str) -> None:
        check_call([self.patchelf_path, "--remove-rpath", file_name])
        check_call([self.patchelf_path, "--force-rpath", "--set-rpath", rpath, file_name])

    def get_rpath(self, file_name: Path) -> str:
        return (
            check_output([self.patchelf_path, "--print-rpath", file_name]).decode("utf-8").strip()
        )
