from __future__ import annotations

import dataclasses
import re
from collections import defaultdict
from itertools import chain
from pathlib import Path
from shutil import which
from subprocess import CalledProcessError, check_call, check_output
from typing import TYPE_CHECKING

from auditwheel.wheeltools import android_api_level

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclasses.dataclass()
class ElfUpdateInfo:
    soname: str | None = None
    rpath: str | None = None
    remove_needed: list[str] = dataclasses.field(default_factory=list)
    replace_needed: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    clear_rpath: bool = False


class ElfPatcher:
    def __init__(self, platform: str) -> None:
        self.platform = platform
        self._updates: dict[str, ElfUpdateInfo] = defaultdict(ElfUpdateInfo)

    @staticmethod
    def _needed_overlap(removed: Iterable[str], replaced: Iterable[tuple[str, str]]) -> str | None:
        for soname in removed:
            for org_soname, new_soname in replaced:
                if soname in (org_soname, new_soname):
                    return soname
        return None

    def replace_needed(self, file_name: Path, *old_new_pairs: tuple[str, str]) -> None:
        key = str(file_name.resolve(strict=True))
        update_info = self._updates[key]
        if overlap_soname := ElfPatcher._needed_overlap(update_info.remove_needed, old_new_pairs):
            msg = f"can't add replace_needed entry, {overlap_soname!r} has been removed"
            raise ValueError(msg)
        update_info.replace_needed.extend(old_new_pairs)

    def remove_needed(self, file_name: Path, *sonames: str) -> None:
        key = str(file_name.resolve(strict=True))
        update_info = self._updates[key]
        if overlap_soname := ElfPatcher._needed_overlap(sonames, update_info.replace_needed):
            msg = f"can't remove {overlap_soname!r} as it's part of the replace_needed entries"
            raise ValueError(msg)
        update_info.remove_needed.extend(sonames)

    def set_soname(self, file_name: Path, new_so_name: str) -> None:
        key = str(file_name.resolve(strict=True))
        self._updates[key].soname = new_so_name

    def set_rpath(self, file_name: Path, rpath: str) -> None:
        # https://android.googlesource.com/platform/bionic/+/refs/heads/main/android-changes-for-ndk-developers.md
        if self.platform.startswith("android") and android_api_level(self.platform) < 24:
            msg = "Grafting libraries with RUNPATH requires API level 24 or higher"
            raise ValueError(msg)
        key = str(file_name.resolve(strict=True))
        self._updates[key].rpath = rpath

    def get_rpath(self, file_name: Path) -> str:
        key = str(file_name.resolve(strict=True))
        if update_info := self._updates.get(key, None):
            if update_info.rpath is not None:
                return update_info.rpath
            if update_info.clear_rpath:
                return ""
        return self.get_rpath_direct(file_name)

    def clear_rpath(self, file_name: Path) -> None:
        key = str(file_name.resolve(strict=True))
        self._updates[key].clear_rpath = True

    def update_elf_path(self, old_file_name: Path, new_file_name: Path) -> None:
        old_key = str(old_file_name.resolve(strict=True))
        new_key = str(new_file_name.resolve(strict=True))
        if old_key in self._updates:
            self._updates[new_key] = self._updates.pop(old_key)

    def get_rpath_direct(self, file_name: Path) -> str:
        raise NotImplementedError

    def apply_updates(self) -> None:
        raise NotImplementedError


def _verify_patchelf() -> Path:
    """This function looks for the ``patchelf`` external binary in the PATH,
    checks for the required version, and throws an exception if a proper
    version can't be found. Otherwise, silence is golden
    """
    patchelf_path = which("patchelf")
    if not patchelf_path:
        msg = "Cannot find required utility `patchelf` in PATH"
        raise ValueError(msg)
    try:
        version = check_output([patchelf_path, "--version"]).decode("utf-8")
    except CalledProcessError:
        msg = "Could not call `patchelf` binary"
        raise ValueError(msg) from None

    m = re.match(r"patchelf\s+(\d+(.\d+)?)", version)
    if m and tuple(int(x) for x in m.group(1).split(".")) >= (0, 14):
        return Path(patchelf_path)
    msg = f"patchelf {version} found. auditwheel repair requires patchelf >= 0.14."
    raise ValueError(msg)


class Patchelf(ElfPatcher):
    def __init__(self, platform: str = "") -> None:
        super().__init__(platform)
        self._patchelf_path = str(_verify_patchelf())

    def get_rpath_direct(self, file_name: Path) -> str:
        args = ("--print-rpath", file_name)
        output = check_output([self._patchelf_path, *args]).decode("utf-8").strip()
        return output.removesuffix(" (legacy)")

    def apply_updates(self) -> None:
        elf_files = list(self._updates.keys())
        for filepath in elf_files:
            # prevent re-applying by removing from self._updates
            update_info = self._updates.pop(filepath)
            args = []
            if update_info.soname is not None:
                args.extend(["--set-soname", update_info.soname])
            if update_info.remove_needed:
                args.extend(
                    chain.from_iterable(
                        ("--remove-needed", soname) for soname in update_info.remove_needed
                    ),
                )
            if update_info.replace_needed:
                args.extend(
                    chain.from_iterable(
                        ("--replace-needed", *pair) for pair in update_info.replace_needed
                    ),
                )
            if update_info.clear_rpath and update_info.rpath is None:
                args.append("--remove-rpath")
            if update_info.rpath is not None:
                set_args = ["--force-rpath", "--set-rpath", update_info.rpath]
                if self.platform.startswith("android"):
                    # Android supports only RUNPATH, not RPATH.
                    set_args.remove("--force-rpath")
                args.extend(set_args)
            if args:
                check_call([self._patchelf_path, *args, filepath])
        assert len(self._updates) == 0  # noqa: S101
