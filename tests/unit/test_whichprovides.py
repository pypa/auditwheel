import subprocess
from typing import ClassVar
from unittest.mock import MagicMock, call, patch

import pytest

from auditwheel._vendor.whichprovides import (
    DpkgPackageProvider,
    PackageProvider,
    ProvidedBy,
    whichprovides,
)
from auditwheel._vendor.whichprovides.__init__ import _candidate_paths_for_filepath


class DummyProvider(PackageProvider):
    _resolve_order = 0
    records: ClassVar[dict[str, ProvidedBy]] = {}
    queried: ClassVar[list[set[str]]] = []

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def whichprovides(cls, filepaths):
        cls.queried.append(set(filepaths))
        return {fp: cls.records[fp] for fp in filepaths if fp in cls.records}


@pytest.fixture(autouse=True)
def clean_dummy_provider():
    DummyProvider.records = {}
    DummyProvider.queried = []


def test_candidate_paths_for_filepath():
    # /lib path has /usr/lib equivalent
    cands_lib = _candidate_paths_for_filepath("/lib/x86_64-linux-gnu/liblzma.so.5.4.1")
    assert cands_lib[0] == "/lib/x86_64-linux-gnu/liblzma.so.5.4.1"
    assert "/usr/lib/x86_64-linux-gnu/liblzma.so.5.4.1" in cands_lib

    # /usr/lib path has /lib equivalent
    cands_usr = _candidate_paths_for_filepath("/usr/lib/x86_64-linux-gnu/liblzma.so.5.4.1")
    assert cands_usr[0] == "/usr/lib/x86_64-linux-gnu/liblzma.so.5.4.1"
    assert "/lib/x86_64-linux-gnu/liblzma.so.5.4.1" in cands_usr


@patch("auditwheel._vendor.whichprovides._package_providers")
def test_whichprovides_queries_original_path_first(mock_providers):
    mock_providers.return_value = [DummyProvider]
    lib_path = "/lib/x86_64-linux-gnu/liblzma.so.5.4.1"
    dummy_pkg = ProvidedBy(
        package_type="deb",
        distro="debian",
        package_name="liblzma5",
        package_version="5.4.1-0.2",
    )
    DummyProvider.records[lib_path] = dummy_pkg

    results = whichprovides([lib_path])

    assert results == {lib_path: dummy_pkg}
    # Only queried once for the original path
    assert len(DummyProvider.queried) == 1
    assert DummyProvider.queried[0] == {lib_path}


@patch("auditwheel._vendor.whichprovides._package_providers")
def test_whichprovides_fallback_to_resolved_path(mock_providers):
    mock_providers.return_value = [DummyProvider]
    symlink_path = "/custom/lib/libfoo.so"
    resolved_path = "/custom/lib/libfoo.so.1.0"
    dummy_pkg = ProvidedBy(
        package_type="deb",
        distro="ubuntu",
        package_name="libfoo",
        package_version="1.0.0",
    )
    # The package only has the resolved realpath, not the symlink
    DummyProvider.records[resolved_path] = dummy_pkg

    with patch("pathlib.Path.resolve", return_value=MagicMock(__str__=lambda _: resolved_path)):
        results = whichprovides([symlink_path])

    assert results == {symlink_path: dummy_pkg}
    # First queried original path, then queried resolved path
    assert len(DummyProvider.queried) == 2
    assert DummyProvider.queried[0] == {symlink_path}
    assert DummyProvider.queried[1] == {resolved_path}


@patch("auditwheel._vendor.whichprovides._package_providers")
def test_whichprovides_usrmerge_fallback(mock_providers):
    mock_providers.return_value = [DummyProvider]
    usr_path = "/usr/lib/x86_64-linux-gnu/liblzma.so.5.4.1"
    lib_path = "/lib/x86_64-linux-gnu/liblzma.so.5.4.1"
    dummy_pkg = ProvidedBy(
        package_type="deb",
        distro="ubuntu",
        package_name="liblzma5",
        package_version="5.4.1-0.2",
    )
    # Deb database only records /lib/ path
    DummyProvider.records[lib_path] = dummy_pkg

    results = whichprovides([usr_path])

    assert results == {usr_path: dummy_pkg}


@patch("auditwheel._vendor.whichprovides._package_providers")
def test_whichprovides_no_key_collision_for_same_resolved_path(mock_providers):
    mock_providers.return_value = [DummyProvider]
    path1 = "/lib/libcublas.so.13"
    path2 = "/lib/libcublas.so.13.1.1.3"
    dummy_pkg = ProvidedBy(
        package_type="rpm",
        distro="almalinux",
        package_name="libcublas",
        package_version="13.1.1.3-1",
    )
    DummyProvider.records[path1] = dummy_pkg
    DummyProvider.records[path2] = dummy_pkg

    results = whichprovides([path1, path2])

    assert path1 in results
    assert path2 in results
    assert results[path1] == dummy_pkg
    assert results[path2] == dummy_pkg


@patch("auditwheel._vendor.whichprovides._package_providers")
def test_whichprovides_single_string_arg(mock_providers):
    mock_providers.return_value = [DummyProvider]
    path = "/bin/bash"
    dummy_pkg = ProvidedBy(
        package_type="deb",
        distro="debian",
        package_name="bash",
        package_version="5.2.15",
    )
    DummyProvider.records[path] = dummy_pkg

    results = whichprovides(path)

    assert results == {path: dummy_pkg}


def test_dpkg_package_provider_parsing_standard():
    with (
        patch.object(DpkgPackageProvider, "which", return_value="/usr/bin/dpkg"),
        patch.object(DpkgPackageProvider, "distro", return_value="debian"),
        patch("subprocess.check_output") as mock_check_output,
    ):
        mock_check_output.side_effect = [
            b"bash: /bin/bash\n",
            b"Package: bash\nVersion: 5.2.15-2+b2\n",
        ]
        result = DpkgPackageProvider.whichprovides1("/bin/bash")

    assert result is not None
    assert result.package_name == "bash"
    assert result.package_version == "5.2.15-2+b2"
    assert result.package_type == "deb"
    assert result.distro == "debian"


def test_dpkg_package_provider_parsing_multiarch():
    with (
        patch.object(DpkgPackageProvider, "which", return_value="/usr/bin/dpkg"),
        patch.object(DpkgPackageProvider, "distro", return_value="ubuntu"),
        patch("subprocess.check_output") as mock_check_output,
    ):
        mock_check_output.side_effect = [
            b"liblzma5:amd64: /lib/x86_64-linux-gnu/liblzma.so.5.4.1\n",
            b"Package: liblzma5\nArchitecture: amd64\nVersion: 5.4.1-0.2\n",
        ]
        result = DpkgPackageProvider.whichprovides1("/lib/x86_64-linux-gnu/liblzma.so.5.4.1")

    assert result is not None
    assert result.package_name == "liblzma5"
    assert result.package_version == "5.4.1-0.2"
    assert result.package_type == "deb"
    assert result.distro == "ubuntu"
    # Verify status query included arch qualifier
    assert mock_check_output.call_args_list == [
        call(
            ["/usr/bin/dpkg", "-S", "/lib/x86_64-linux-gnu/liblzma.so.5.4.1"],
            stderr=subprocess.DEVNULL,
        ),
        call(["/usr/bin/dpkg", "-s", "liblzma5:amd64"], stderr=subprocess.DEVNULL),
    ]


def test_dpkg_package_provider_parsing_diversion():
    diversion_output = (
        b"diversion by dash from: /bin/sh\ndiversion by dash to: /bin/sh.distrib\ndash: /bin/sh\n"
    )
    with (
        patch.object(DpkgPackageProvider, "which", return_value="/usr/bin/dpkg"),
        patch.object(DpkgPackageProvider, "distro", return_value="debian"),
        patch("subprocess.check_output") as mock_check_output,
    ):
        mock_check_output.side_effect = [
            diversion_output,
            b"Package: dash\nVersion: 0.5.12-6\n",
        ]
        result = DpkgPackageProvider.whichprovides1("/bin/sh")

    assert result is not None
    assert result.package_name == "dash"
    assert result.package_version == "0.5.12-6"
