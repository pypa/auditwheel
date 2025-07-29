# SPDX-License-Identifier: MIT

"""
Module which provides (heh) 'yum provides'
functionality across many package managers.
"""

import dataclasses
import pathlib
import re
import shutil
import subprocess
import sys
import typing
from urllib.parse import quote

__all__ = ["ProvidedBy", "whichprovides"]
__version__ = "0.4.0"

_OS_RELEASE_LINES_RE = re.compile(r"^([A-Z_]+)=(?:\"([^\"]*)\"|(.*))$", re.MULTILINE)
_APK_WHO_OWNS_RE = re.compile(r" is owned by ([^\s\-]+)-([^\s]+)$", re.MULTILINE)
_DPKG_SEARCH_RE = re.compile(r"^([^:]+):")
_DPKG_VERSION_RE = re.compile(r"^Version: ([^\s]+)", re.MULTILINE)
_APT_FILE_SEARCH_RE = re.compile(r"^([^:]+): (.+)$", re.MULTILINE)


@dataclasses.dataclass
class ProvidedBy:
    package_type: str
    package_name: str
    package_version: str
    distro: typing.Union[str, None] = None

    @property
    def purl(self) -> str:
        """The Package URL (PURL) of the providing package"""

        def _quote_purl(value: str) -> str:
            """
            Quotes according to PURL rules which are different from
            typical URL percent encoding.
            """
            return quote(value, safe="")

        # PURL disallows many characters in the package type field.
        if not re.match(r"^[a-zA-Z0-9\+\-\.]+$", self.package_type):
            raise ValueError("Package type must be ASCII letters, numbers, +, -, and .")

        parts = ["pkg:", self.package_type.lower(), "/"]
        if self.distro:
            parts.extend((_quote_purl(self.distro), "/"))
        parts.extend(
            (_quote_purl(self.package_name), "@", _quote_purl(self.package_version))
        )
        return "".join(parts)


class PackageProvider:
    # Order in which the provider should be resolved.
    # Lower is attempted earlier than higher numbers.
    _resolve_order: int = 0
    _has_bin_cache: dict[str, typing.Union[str, bool]] = {}

    @staticmethod
    def os_release() -> dict[str, str]:
        """Dumb method of finding os-release information."""
        try:
            with open("/etc/os-release") as f:
                os_release = {}
                for name, value_quoted, value_unquoted in _OS_RELEASE_LINES_RE.findall(
                    f.read()
                ):
                    value = value_quoted if value_quoted else value_unquoted
                    os_release[name] = value
                return os_release
        except OSError:
            return {}

    @staticmethod
    def distro() -> typing.Optional[str]:
        return PackageProvider.os_release().get("ID", None)

    @classmethod
    def which(
        cls, bin: str, *, allowed_returncodes: typing.Optional[set[int]] = None
    ) -> typing.Optional[str]:
        """which, but tries to execute the program, too!"""
        cached_bin = cls._has_bin_cache.get(bin)
        assert cached_bin is not True
        if cached_bin is False:
            return None
        if cached_bin is not None:
            return cached_bin
        bin_which = shutil.which(bin)
        if bin_which is None:  # Cache the 'not-found' result.
            cls._has_bin_cache[bin] = False
            return None
        try:
            subprocess.check_call(
                [bin_which, "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            cls._has_bin_cache[bin] = bin_which
            return bin_which
        except subprocess.CalledProcessError as e:
            # If running --version returns an non-zero exit we
            # explicitly allow that here.
            if allowed_returncodes and e.returncode in allowed_returncodes:
                cls._has_bin_cache[bin] = bin_which
                return bin_which
            cls._has_bin_cache[bin] = False
        return None

    @classmethod
    def is_available(cls) -> bool:
        return False

    @classmethod
    def whichprovides(cls, filepaths: typing.Collection[str]) -> dict[str, ProvidedBy]:
        raise NotImplementedError()


class _SinglePackageProvider(PackageProvider):
    """Abstract PackageProvider for single-filepath APIs"""

    @classmethod
    def whichprovides(cls, filepaths: typing.Collection[str]) -> dict[str, ProvidedBy]:
        results = {}
        for filepath in filepaths:
            if provided_by := cls.whichprovides1(filepath):
                results[filepath] = provided_by
        return results

    @classmethod
    def whichprovides1(cls, filepath: str) -> typing.Optional[ProvidedBy]:
        raise NotImplementedError()


class ApkPackageProvider(_SinglePackageProvider):
    @classmethod
    def is_available(cls) -> bool:
        return bool(cls.which("apk") and cls.distro())

    @classmethod
    def whichprovides1(cls, filepath: str) -> typing.Optional[ProvidedBy]:
        apk_bin = cls.which("apk")
        distro = cls.distro()
        assert apk_bin is not None and distro is not None
        try:
            # $ apk info --who-owns /bin/bash
            # /bin/bash is owned by bash-5.2.26-r0
            stdout = subprocess.check_output(
                [apk_bin, "info", "--who-owns", str(filepath)],
                stderr=subprocess.DEVNULL,
            ).decode()
            if match := _APK_WHO_OWNS_RE.search(stdout):
                return ProvidedBy(
                    package_type="apk",
                    distro=distro,
                    package_name=match.group(1),
                    package_version=match.group(2),
                )
        except subprocess.CalledProcessError:
            pass
        return None


class RpmPackageProvider(_SinglePackageProvider):
    @classmethod
    def is_available(cls) -> bool:
        return bool(cls.which("rpm") and cls.distro())

    @classmethod
    def whichprovides1(cls, filepath: str) -> typing.Optional[ProvidedBy]:
        rpm_bin = cls.which("rpm")
        distro = cls.distro()
        assert rpm_bin is not None and distro is not None
        try:
            # $ rpm -qf --queryformat "%{NAME} %{VERSION} %{RELEASE} ${ARCH}" /bin/bash
            # bash 4.4.20 4.el8_6
            stdout = subprocess.check_output(
                [
                    rpm_bin,
                    "-qf",
                    "--queryformat",
                    "%{NAME} %{VERSION} %{RELEASE} %{ARCH}",
                    str(filepath),
                ],
                stderr=subprocess.DEVNULL,
            ).decode()
            package_name, package_version, package_release, *_ = stdout.strip().split(
                " ", 4
            )
            return ProvidedBy(
                package_type="rpm",
                distro=distro,
                package_name=package_name,
                package_version=f"{package_version}-{package_release}",
            )
        except subprocess.CalledProcessError:
            pass
        return None


class DpkgPackageProvider(_SinglePackageProvider):
    @classmethod
    def is_available(cls) -> bool:
        return bool(cls.which("dpkg") and cls.distro())

    @classmethod
    def whichprovides1(cls, filepath: str) -> typing.Optional[ProvidedBy]:
        dpkg_bin = cls.which("dpkg")
        distro = cls.distro()
        assert dpkg_bin is not None and distro is not None
        try:
            # $ dpkg -S /bin/bash
            # bash: /bin/bash
            stdout = subprocess.check_output(
                [dpkg_bin, "-S", str(filepath)],
                stderr=subprocess.DEVNULL,
            ).decode()
            if match := _DPKG_SEARCH_RE.search(stdout):
                package_name = match.group(1)
                # $ dpkg -s bash
                # ...
                # Version: 5.1-6ubuntu1.1
                stdout = subprocess.check_output(
                    [dpkg_bin, "-s", package_name],
                    stderr=subprocess.DEVNULL,
                ).decode()
                if match := _DPKG_VERSION_RE.search(stdout):
                    return ProvidedBy(
                        package_type="deb",
                        distro=distro,
                        package_name=package_name,
                        package_version=match.group(1),
                    )
        except subprocess.CalledProcessError:
            pass
        return None


class AptFilePackageProvider(PackageProvider):
    # apt-file is slow, so resolve this one later.
    _resolve_order = 100

    @classmethod
    def is_available(cls) -> bool:
        return bool(
            cls.which("apt")
            and cls.which("apt-file", allowed_returncodes={2})
            and cls.distro()
        )

    @classmethod
    def whichprovides(cls, filepaths: typing.Collection[str]) -> dict[str, ProvidedBy]:
        apt_bin = cls.which("apt")
        apt_file_bin = cls.which("apt-file", allowed_returncodes={2})
        distro = cls.distro()
        assert apt_bin is not None and apt_file_bin is not None and distro is not None
        results = {}
        try:
            # $ echo '\n'.join(paths) | apt-file search --from-file -
            # Finding relevant cache files to search ...
            # ...
            # libwebpdemux2: /usr/lib/x86_64-linux-gnu/libwebpdemux.so.2.0.9
            stdout = subprocess.check_output(
                [apt_file_bin, "search", "--from-file", "-"],
                stderr=subprocess.DEVNULL,
                input=b"\n".join(
                    [str(filepath).encode("utf-8") for filepath in filepaths]
                ),
            ).decode()
            for package_name, filepath in _APT_FILE_SEARCH_RE.findall(stdout):
                stdout = subprocess.check_output(
                    [apt_bin, "show", package_name],
                    stderr=subprocess.DEVNULL,
                ).decode()
                if match := _DPKG_VERSION_RE.search(stdout):
                    package_version = match.group(1)
                    results[filepath] = ProvidedBy(
                        package_type="deb",
                        distro=distro,
                        package_name=package_name,
                        package_version=package_version,
                    )
        except subprocess.CalledProcessError:
            pass
        return results


def _package_providers() -> list[type[PackageProvider]]:
    """Returns a list of package providers sorted in
    the order that they should be attempted.
    """

    def all_subclasses(cls):
        subclasses = set()
        for subcls in cls.__subclasses__():
            subclasses.add(subcls)
            subclasses |= all_subclasses(subcls)
        return subclasses

    return sorted(all_subclasses(PackageProvider), key=lambda p: p._resolve_order)


def whichprovides(filepath: typing.Union[str, list[str]]) -> dict[str, ProvidedBy]:
    """Return a package URL (PURL) for the package that provides a file"""
    if isinstance(filepath, str):
        filepaths = [filepath]
    else:
        filepaths = filepath

    # Link between the original path to the resolved
    # path and then allocate a structure for results.
    resolved_filepaths = {
        str(pathlib.Path(filepath).resolve()): filepath for filepath in filepaths
    }
    filepath_provided_by: dict[str, ProvidedBy] = {}
    for package_provider in _package_providers():
        remaining = set(resolved_filepaths) - set(filepath_provided_by)
        if not remaining:
            break
        if not package_provider.is_available():
            continue
        results = package_provider.whichprovides(remaining)
        filepath_provided_by.update(results)

    return {
        resolved_filepaths[filepath]: value
        for filepath, value in filepath_provided_by.items()
    }


def _main():
    if len(sys.argv) < 2:
        print(
            "Must provide one or more path argument "
            "('$ python -m whichprovides <paths>')",
            file=sys.stderr,
        )
        sys.exit(1)

    filepaths = sys.argv[1:]
    provided_bys = whichprovides(filepaths)
    exit_code = 0
    for filepath in filepaths:
        provided_by = provided_bys.get(filepath)
        if provided_by:
            print(f"{filepath}: {provided_by.purl}")
        else:
            print(f"No known package providing {filepath}", file=sys.stderr)
            exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    _main()
