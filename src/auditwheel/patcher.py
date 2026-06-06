from __future__ import annotations

import re
from itertools import chain
from shutil import which
from subprocess import CalledProcessError, check_call, check_output
from typing import TYPE_CHECKING

from auditwheel.wheeltools import android_api_level

if TYPE_CHECKING:
    from pathlib import Path


class ElfPatcher:
    def __init__(self, platform: str) -> None:
        self.platform = platform

    def replace_needed(self, file_name: Path, *old_new_pairs: tuple[str, str]) -> None:
        raise NotImplementedError

    def remove_needed(self, file_name: Path, *sonames: str) -> None:
        raise NotImplementedError

    def set_soname(self, file_name: Path, new_so_name: str) -> None:
        raise NotImplementedError

    def check_rpath_support(self) -> None:
        # https://android.googlesource.com/platform/bionic/+/refs/heads/main/android-changes-for-ndk-developers.md
        if self.platform.startswith("android") and android_api_level(self.platform) < 24:
            msg = "Grafting libraries with RUNPATH requires API level 24 or higher"
            raise ValueError(msg)

    def set_rpath(self, file_name: Path, rpath: str) -> None:
        raise NotImplementedError

    def get_rpath(self, file_name: Path) -> str:
        raise NotImplementedError

    def clear_rpath(self, file_name: Path) -> None:
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
    def __init__(self, platform: str = "", *, allow_lief: bool = True) -> None:
        super().__init__(platform)
        self.patchelf_path = _verify_patchelf(allow_lief=allow_lief)

    def _check_call(self, *args: str | Path) -> None:
        check_call([self.patchelf_path, *args])

    def _check_output(self, *args: str | Path) -> str:
        return check_output([self.patchelf_path, *args]).decode("utf-8").strip()

    def replace_needed(self, file_name: Path, *old_new_pairs: tuple[str, str]) -> None:
        self._check_call(
            *chain.from_iterable(("--replace-needed", *pair) for pair in old_new_pairs),
            file_name,
        )

    def remove_needed(self, file_name: Path, *sonames: str) -> None:
        self._check_call(
            *chain.from_iterable(("--remove-needed", soname) for soname in sonames),
            file_name,
        )

    def set_soname(self, file_name: Path, new_so_name: str) -> None:
        self._check_call("--set-soname", new_so_name, file_name)

    def set_rpath(self, file_name: Path, rpath: str) -> None:
        self.check_rpath_support()

        set_args: list[str | Path] = ["--force-rpath", "--set-rpath", rpath, file_name]
        if self.platform.startswith("android"):
            # Android supports only RUNPATH, not RPATH.
            set_args.remove("--force-rpath")

        # we only want an RPATH, remove RUNPATH/RPATH altogether in a 1st pass
        self._check_call("--remove-rpath", file_name)
        self._check_call(*set_args)

    def get_rpath(self, file_name: Path) -> str:
        return self._check_output("--print-rpath", file_name)

    def clear_rpath(self, file_name: Path) -> None:
        self._check_call("--remove-rpath", file_name)
