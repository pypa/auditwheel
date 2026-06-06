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
    from typing import Literal

    PatchElfVariants = Literal["patchelf", "lief-patchelf"]


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
        self._updates: dict[Path, ElfUpdateInfo] = defaultdict(ElfUpdateInfo)

    @staticmethod
    def _needed_overlap(removed: Iterable[str], replaced: Iterable[tuple[str, str]]) -> str | None:
        replaced_sonames = set(chain.from_iterable(replaced))
        return next((name for name in removed if name in replaced_sonames), None)

    def _update_for(self, file_name: Path) -> ElfUpdateInfo:
        return self._updates[file_name.resolve(strict=True)]

    def replace_needed(self, file_name: Path, *old_new_pairs: tuple[str, str]) -> None:
        update_info = self._update_for(file_name)
        if overlap_soname := ElfPatcher._needed_overlap(update_info.remove_needed, old_new_pairs):
            msg = f"can't add replace_needed entry, {overlap_soname!r} has been removed"
            raise ValueError(msg)
        update_info.replace_needed.extend(old_new_pairs)

    def remove_needed(self, file_name: Path, *sonames: str) -> None:
        update_info = self._update_for(file_name)
        if overlap_soname := ElfPatcher._needed_overlap(sonames, update_info.replace_needed):
            msg = f"can't remove {overlap_soname!r} as it's part of the replace_needed entries"
            raise ValueError(msg)
        update_info.remove_needed.extend(sonames)

    def set_soname(self, file_name: Path, new_so_name: str) -> None:
        self._update_for(file_name).soname = new_so_name

    def set_rpath(self, file_name: Path, rpath: str) -> None:
        # https://android.googlesource.com/platform/bionic/+/refs/heads/main/android-changes-for-ndk-developers.md
        if self.platform.startswith("android") and android_api_level(self.platform) < 24:
            msg = "Grafting libraries with RUNPATH requires API level 24 or higher"
            raise ValueError(msg)
        self._update_for(file_name).rpath = rpath

    def get_rpath(self, file_name: Path) -> str:
        key = file_name.resolve(strict=True)
        if update_info := self._updates.get(key, None):
            if update_info.rpath is not None:
                return update_info.rpath
            if update_info.clear_rpath:
                return ""
        return self.get_rpath_direct(file_name)

    def clear_rpath(self, file_name: Path) -> None:
        self._update_for(file_name).clear_rpath = True

    def update_elf_path(self, old_file_name: Path, new_file_name: Path) -> None:
        old_key = old_file_name.resolve(strict=True)
        if old_key in self._updates:
            new_key = new_file_name.resolve(strict=True)
            self._updates[new_key] = self._updates.pop(old_key)

    def get_rpath_direct(self, file_name: Path) -> str:
        raise NotImplementedError

    def apply_updates(self) -> None:
        raise NotImplementedError

    @staticmethod
    def get_patcher(allowed_patchers: Iterable[str], platform: str = "") -> ElfPatcher:
        allowed_patchers_ = list(allowed_patchers)
        exceptions = []
        for allowed_patcher in allowed_patchers_:
            match allowed_patcher:
                case "patchelf" | "lief-patchelf":
                    try:
                        return _Patchelf(variant=allowed_patcher, platform=platform)
                    except ValueError as e:
                        exceptions.append(e)
                case "none":
                    return _NonePatcher(platform=platform)
                case _:
                    msg = f"Unknown patcher {allowed_patcher!r}"
                    exceptions.append(ValueError(msg))
        if not exceptions:
            msg = "At least one patcher shall be specified."
            exceptions.append(ValueError(msg))
        msg = f"Could not find a working patcher in {', '.join(allowed_patchers_)!r}"
        # TODO move to exception group with Python 3.11+
        exceptions_str = "\n".join(str(e) for e in exceptions)
        msg = f"{msg}. The following exceptions were found:\n{exceptions_str}"
        raise ValueError(msg)


class _NonePatcher(ElfPatcher):
    def apply_updates(self) -> None:
        elf_files = list(self._updates.keys())
        errors = []
        for filepath in elf_files:
            # prevent re-applying by removing from self._updates
            update_info = self._updates.pop(filepath)
            if (
                update_info.soname is not None
                or update_info.remove_needed
                or update_info.replace_needed
                or update_info.clear_rpath
                or update_info.rpath is not None
            ):
                errors.append(filepath)
        assert len(self._updates) == 0  # noqa: S101
        if errors:
            errors_str = "\n".join(str(e) for e in errors)
            msg = f"The 'none' patcher can't patch the following files:\n{errors_str}"
            raise NotImplementedError(msg)


def _verify_patchelf(variant: PatchElfVariants) -> Path:
    """This function looks for the ``patchelf`` external binary in the PATH,
    checks for the required version, and throws an exception if a proper
    version can't be found. Otherwise, silence is golden
    """
    patchelf_path = which(variant)
    if not patchelf_path:
        msg = f"Cannot find required utility {variant!r} in PATH"
        raise ValueError(msg)
    if variant == "lief-patchelf":
        return Path(patchelf_path)
    try:
        version = check_output([patchelf_path, "--version"]).decode("utf-8")
    except CalledProcessError:
        msg = "Could not call `patchelf` binary"
        raise ValueError(msg) from None

    m = re.match(r"patchelf\s+(\d+(.\d+)?)", version)
    if m and tuple(int(x) for x in m.group(1).split(".")) >= (0, 14):
        return Path(patchelf_path)
    msg = f"{version.strip()} found. auditwheel repair requires patchelf >= 0.14."
    raise ValueError(msg)


class _Patchelf(ElfPatcher):
    def __init__(self, variant: PatchElfVariants, platform: str = "") -> None:
        super().__init__(platform)
        self._patchelf_path = str(_verify_patchelf(variant))

    def get_rpath_direct(self, file_name: Path) -> str:
        output = check_output([self._patchelf_path, "--print-rpath", file_name])
        return output.decode("utf-8").strip().removesuffix(" (legacy)")

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
