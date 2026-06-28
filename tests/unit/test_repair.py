from __future__ import annotations

from pathlib import Path

from auditwheel.patcher import ElfPatcher
from auditwheel.repair import append_rpath_within_wheel


class MockedElfPatcher(ElfPatcher):
    def __init__(self, existing_rpath: str) -> None:
        super().__init__("")
        self._existing_rpath = existing_rpath
        self.get_rpath_direct_called: list[Path] = []

    def get_rpath_direct(self, file_name: Path) -> str:
        self.get_rpath_direct_called.append(file_name)
        return self._existing_rpath


def test_append_rpath(tmp_path: Path) -> None:
    # When a library has an existing RPATH entry within wheel_dir
    existing_rpath = "$ORIGIN/.existinglibdir"
    patcher = MockedElfPatcher(existing_rpath)
    wheel_dir = tmp_path
    lib_name = tmp_path / "test.so"
    lib_name.touch()
    full_lib_name = lib_name.absolute()
    lib_name_str = str(lib_name.resolve(strict=True))
    append_rpath_within_wheel(lib_name, "$ORIGIN/.lib", wheel_dir, patcher)
    # Then that entry is preserved when updating the RPATH
    assert patcher.get_rpath_direct_called == [full_lib_name]
    assert patcher._updates[lib_name_str].rpath == f"{existing_rpath}:$ORIGIN/.lib"


def test_append_rpath_reject_outside_wheel(tmp_path: Path) -> None:
    # When a library has an existing RPATH entry outside wheel_dir
    existing_rpath = "/outside/wheel/dir"
    patcher = MockedElfPatcher(existing_rpath)
    wheel_dir = Path("/not/outside")
    lib_name = tmp_path / "test.so"
    lib_name.touch()
    full_lib_name = lib_name.absolute()
    lib_name_str = str(lib_name.resolve(strict=True))
    append_rpath_within_wheel(lib_name, "$ORIGIN/.lib", wheel_dir, patcher)
    # Then that entry is eliminated when updating the RPATH
    assert patcher.get_rpath_direct_called == [full_lib_name]
    assert patcher._updates[lib_name_str].rpath == "$ORIGIN/.lib"


def test_append_rpath_ignore_duplicates(tmp_path: Path) -> None:
    # When a library has an existing RPATH entry and we try and append it again
    existing_rpath = "$ORIGIN"
    patcher = MockedElfPatcher(existing_rpath)
    wheel_dir = tmp_path
    lib_name = tmp_path / "test.so"
    lib_name.touch()
    full_lib_name = lib_name.absolute()
    lib_name_str = str(lib_name.resolve(strict=True))
    append_rpath_within_wheel(lib_name, "$ORIGIN", wheel_dir, patcher)
    # Then that entry is ignored when updating the RPATH
    assert patcher.get_rpath_direct_called == [full_lib_name]
    assert patcher._updates[lib_name_str].rpath == "$ORIGIN"


def test_append_rpath_ignore_relative(tmp_path: Path) -> None:
    # When a library has an existing RPATH entry but it cannot be resolved
    # to an absolute path, it is eliminated
    existing_rpath = "not/absolute"
    patcher = MockedElfPatcher(existing_rpath)
    wheel_dir = tmp_path
    lib_name = tmp_path / "test.so"
    lib_name.touch()
    full_lib_name = lib_name.absolute()
    lib_name_str = str(lib_name.resolve(strict=True))
    append_rpath_within_wheel(lib_name, "$ORIGIN", wheel_dir, patcher)
    # Then that entry is ignored when updating the RPATH
    assert patcher.get_rpath_direct_called == [full_lib_name]
    assert patcher._updates[lib_name_str].rpath == "$ORIGIN"
