from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import sys
import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from subprocess import CalledProcessError
from typing import Any

import docker
import pytest
from docker.models.containers import Container
from elftools.elf.elffile import ELFFile

from auditwheel.architecture import Architecture
from auditwheel.libc import Libc
from auditwheel.policy import WheelPolicies

logger = logging.getLogger(__name__)

PLATFORM = os.environ.get("AUDITWHEEL_ARCH", Architecture.detect().value)
MANYLINUX2010_IMAGE_ID = f"quay.io/pypa/manylinux2010_{PLATFORM}:latest"
MANYLINUX2014_IMAGE_ID = f"quay.io/pypa/manylinux2014_{PLATFORM}:latest"
MANYLINUX_2_28_IMAGE_ID = f"quay.io/pypa/manylinux_2_28_{PLATFORM}:latest"
MANYLINUX_2_31_IMAGE_ID = f"quay.io/pypa/manylinux_2_31_{PLATFORM}:latest"
MANYLINUX_2_34_IMAGE_ID = f"quay.io/pypa/manylinux_2_34_{PLATFORM}:latest"
MANYLINUX_2_35_IMAGE_ID = f"quay.io/pypa/manylinux_2_35_{PLATFORM}:latest"
MANYLINUX_2_39_IMAGE_ID = f"quay.io/pypa/manylinux_2_39_{PLATFORM}:latest"
if PLATFORM in {"i686", "x86_64"}:
    MANYLINUX_IMAGES = {
        "manylinux_2_12": MANYLINUX2010_IMAGE_ID,
        "manylinux_2_17": MANYLINUX2014_IMAGE_ID,
        "manylinux_2_28": MANYLINUX_2_28_IMAGE_ID,
        "manylinux_2_34": MANYLINUX_2_34_IMAGE_ID,
    }
    POLICY_ALIASES = {
        "manylinux_2_5": ["manylinux1"],
        "manylinux_2_12": ["manylinux2010"],
        "manylinux_2_17": ["manylinux2014"],
    }
elif PLATFORM == "armv7l":
    MANYLINUX_IMAGES = {
        "manylinux_2_31": MANYLINUX_2_31_IMAGE_ID,
        "manylinux_2_35": MANYLINUX_2_35_IMAGE_ID,
    }
    POLICY_ALIASES = {}
elif PLATFORM == "riscv64":
    MANYLINUX_IMAGES = {"manylinux_2_39": MANYLINUX_2_39_IMAGE_ID}
    POLICY_ALIASES = {}
else:
    MANYLINUX_IMAGES = {
        "manylinux_2_17": MANYLINUX2014_IMAGE_ID,
        "manylinux_2_28": MANYLINUX_2_28_IMAGE_ID,
    }
    if os.environ.get("AUDITWHEEL_QEMU", "") != "true":
        MANYLINUX_IMAGES.update({"manylinux_2_34": MANYLINUX_2_34_IMAGE_ID})
        if PLATFORM == "aarch64":
            MANYLINUX_IMAGES.update({"manylinux_2_39": MANYLINUX_2_39_IMAGE_ID})
    POLICY_ALIASES = {
        "manylinux_2_17": ["manylinux2014"],
    }
DOCKER_CONTAINER_NAME = "auditwheel-test-anylinux"
PYTHON_MAJ_MIN = [str(i) for i in sys.version_info[:2]]
PYTHON_ABI_MAJ_MIN = "".join(PYTHON_MAJ_MIN)
PYTHON_ABI = f"cp{PYTHON_ABI_MAJ_MIN}-cp{PYTHON_ABI_MAJ_MIN}"
PYTHON_IMAGE_TAG = ".".join(PYTHON_MAJ_MIN) + (
    "-rc" if PYTHON_ABI_MAJ_MIN == "314" else ""
)
MANYLINUX_PYTHON_IMAGE_ID = f"python:{PYTHON_IMAGE_TAG}-slim-trixie"
MUSLLINUX_IMAGES = {
    "musllinux_1_2": f"quay.io/pypa/musllinux_1_2_{PLATFORM}:latest",
}
MUSLLINUX_PYTHON_IMAGE_ID = f"python:{PYTHON_IMAGE_TAG}-alpine"
DEVTOOLSET = {
    "manylinux_2_12": "devtoolset-8",
    "manylinux_2_17": "devtoolset-10",
    "manylinux_2_28": "gcc-toolset-14",
    "manylinux_2_31": "devtoolset-not-present",
    "manylinux_2_34": "gcc-toolset-14",
    "manylinux_2_35": "devtoolset-not-present",
    "manylinux_2_39": "devtoolset-not-present",
    "musllinux_1_2": "devtoolset-not-present",
}
PATH_DIRS = [
    f"/opt/python/{PYTHON_ABI}/bin",
    "/opt/rh/{devtoolset}/root/usr/bin",
    "/usr/local/sbin",
    "/usr/local/bin",
    "/usr/sbin",
    "/usr/bin",
    "/sbin",
    "/bin",
]
PATH = {k: ":".join(PATH_DIRS).format(devtoolset=v) for k, v in DEVTOOLSET.items()}
WHEEL_CACHE_FOLDER = Path.home().joinpath(".cache", "auditwheel_tests")
HERE = Path(__file__).parent.resolve(strict=True)
NUMPY_VERSION_MAP = {
    "310": "1.21.4",
    "311": "1.23.4",
    "312": "1.26.4",
    "313": "2.0.1",
    "314": "2.3.2",
}
NUMPY_VERSION = NUMPY_VERSION_MAP[PYTHON_ABI_MAJ_MIN]
ORIGINAL_NUMPY_WHEEL = f"numpy-{NUMPY_VERSION}-{PYTHON_ABI}-linux_{PLATFORM}.whl"
SHOW_RE = re.compile(
    r'.*[\s](?P<wheel>\S+) is consistent with the following platform tag: "(?P<tag>\S+)".*',
    flags=re.DOTALL,
)
TAG_RE = re.compile(r"^manylinux_(?P<major>[0-9]+)_(?P<minor>[0-9]+)_(?P<arch>\S+)$")


class AnyLinuxContainer:
    def __init__(self, policy: str, tag: str, container: Container, io_folder: Path):
        self._policy = policy
        self._tag = tag
        self._container = container
        self._io_folder = io_folder

    @property
    def policy(self):
        return self._policy

    @property
    def io_folder(self):
        return self._io_folder

    def exec(
        self,
        cmd: str | list[str],
        *,
        expected_retcode: int = 0,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        return docker_exec(
            self._container, cmd, expected_retcode=expected_retcode, cwd=cwd, env=env
        )

    def show(
        self,
        wheel: str,
        *,
        verbose: bool = False,
        isa_ext_check: bool = True,
        expected_retcode: int = 0,
    ) -> str:
        isa_ext_check_arg = "" if isa_ext_check else "--disable-isa-ext-check"
        verbose_arg = "-v" if verbose else ""
        cmd = f"auditwheel {verbose_arg} show {isa_ext_check_arg} /io/{wheel}"
        return self.exec(cmd, expected_retcode=expected_retcode)

    def repair(
        self,
        wheel: str,
        *,
        isa_ext_check: bool = True,
        expected_retcode: int = 0,
        plat: str | None = None,
        only_plat: bool = True,
        strip: bool = False,
        library_paths: list[str] | None = None,
        excludes: list[str] | None = None,
    ) -> str:
        plat = plat or self._policy
        args = []
        if library_paths:
            ld_library_path = ":".join([*library_paths, "$LD_LIBRARY_PATH"])
            args.append(f"LD_LIBRARY_PATH={ld_library_path}")
        args.extend(["auditwheel", "repair", "-w", "/io", "--plat", plat])
        if only_plat:
            args.append("--only-plat")
        if not isa_ext_check:
            args.append("--disable-isa-ext-check")
        if strip:
            args.append("--strip")
        if excludes:
            args.extend(f"--exclude={exclude}" for exclude in excludes)
        args.append(f"/io/{wheel}")
        cmd = ["bash", "-c", " ".join(args)]
        return self.exec(cmd, expected_retcode=expected_retcode)

    def build_wheel(
        self,
        path: str,
        *,
        pre_wheel_cmd: str | None = None,
        env: dict[str, str] | None = None,
        check_filename: bool = True,
    ) -> str:
        args = ["if [ -d ./build ]; then rm -rf ./build ./*.egg-info; fi"]
        if pre_wheel_cmd:
            args.append(pre_wheel_cmd)
        args.append("python -m pip wheel --no-deps -w /io .")
        cmd = " && ".join(args)
        self.exec(["bash", "-c", cmd], cwd=path, env=env)

        filenames = os.listdir(self._io_folder)
        assert len(filenames) == 1
        orig_wheel = filenames[0]
        if check_filename:
            assert orig_wheel.endswith(f"-{PYTHON_ABI}-linux_{PLATFORM}.whl")
        assert "manylinux" not in orig_wheel
        assert "musllinux" not in orig_wheel
        return orig_wheel

    def check_wheel(
        self,
        name: str,
        *,
        version: str | None = None,
        python_abi: str | None = None,
        platform_tag: str | None = None,
    ) -> str:
        version = version or "0.0.1"
        python_abi = python_abi or PYTHON_ABI
        platform_tag = platform_tag or self._tag
        repaired_wheel = f"{name}-{version}-{python_abi}-{platform_tag}.whl"
        filenames = os.listdir(self._io_folder)
        assert len(filenames) == 2
        assert repaired_wheel in filenames
        return repaired_wheel

    @property
    def cache_dir(self) -> Path:
        return WHEEL_CACHE_FOLDER / self._policy


class PythonContainer:
    def __init__(self, container: Container):
        self._container = container

    def pip_install(self, args: str) -> str:
        cmd = f"pip install {args}"
        return self.exec(cmd)

    def install_wheel(self, filename: str) -> str:
        return self.pip_install(f"/io/{filename}")

    def run(self, cmd: str, *, env: dict[str, str] | None = None) -> str:
        args: str | list[str]
        if cmd.startswith(("from ", "import ")):
            # run python code
            args = ["python", "-c", cmd]
        else:
            args = f"python {cmd}"
        return self.exec(args, env=env)

    def exec(
        self,
        cmd: str | list[str],
        expected_retcode: int = 0,
        env: dict[str, str] | None = None,
    ) -> str:
        return docker_exec(
            self._container, cmd, expected_retcode=expected_retcode, env=env
        )


def find_src_folder() -> Path | None:
    candidate = HERE.parent.parent.resolve(strict=True)
    contents = os.listdir(candidate)
    if "pyproject.toml" in contents and "src" in contents:
        return candidate
    return None


def docker_start(
    image: str,
    volumes: dict[str, str] | None = None,
    env_variables: dict[str, str] | None = None,
) -> Container:
    """Start a long waiting idle program in container

    Return the container object to be used for 'docker exec' commands.
    """
    # Make sure to use the latest public version of the docker image
    if env_variables is None:
        env_variables = {}
    if volumes is None:
        volumes = {}
    client = docker.from_env()

    dvolumes = {host: {"bind": ctr, "mode": "rw"} for (ctr, host) in volumes.items()}
    goarch = {
        "x86_64": "amd64",
        "i686": "386",
        "aarch64": "arm64",
        "armv7l": "arm/v7",
    }.get(PLATFORM, PLATFORM)

    logger.info("Starting container with image %r", image)
    con = client.containers.run(
        image,
        ["tail", "-f", "/dev/null"],
        detach=True,
        volumes=dvolumes,
        environment=env_variables,
        platform=f"linux/{goarch}",
        working_dir="/auditwheel_src" if "/auditwheel_src" in volumes else None,
    )
    assert isinstance(con.id, str)
    logger.info("Started container %s", con.id[:12])
    return con


@contextmanager
def docker_container_ctx(
    image: str, io_dir: Path | None = None, env_variables: dict[str, str] | None = None
) -> Generator[Container, None, None]:
    src_folder = find_src_folder()
    if src_folder is None:
        pytest.skip("Can only be run from the source folder")
    assert src_folder is not None

    if env_variables is None:
        env_variables = {}
    vols = {"/auditwheel_src": str(src_folder)}
    if io_dir is not None:
        vols["/io"] = str(io_dir)

    container = docker_start(image, vols, env_variables)
    try:
        yield container
    finally:
        container.remove(force=True)


def docker_exec(
    container: Container,
    cmd: str | list[str],
    *,
    expected_retcode: int = 0,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> str:
    assert isinstance(container.id, str)
    logger.info("docker exec %s: %r", container.id[:12], cmd)
    ec, output = container.exec_run(cmd, workdir=cwd, environment=env)
    output = output.decode("utf-8")
    if ec != expected_retcode:
        logger.info("docker exec error %s: %s", container.id[:12], output)
        raise CalledProcessError(ec, cmd, output=output)
    return output


@contextmanager
def tmp_docker_image(
    base: str, commands: list[str], setup_env: dict[str, str] | None = None
) -> Generator[Any, None, None]:
    """Make a temporary docker image for tests

    Pulls the *base* image, runs *commands* inside it with *setup_env*, and
    commits the result as a new image. The image is removed on exiting the
    context.

    Making temporary images like this avoids each test having to re-run the
    same container setup steps.
    """
    if setup_env is None:
        setup_env = {}
    with docker_container_ctx(base, env_variables=setup_env) as con:
        for cmd in commands:
            docker_exec(con, cmd)
        image = con.commit()

    logger.info("Made image %s based on %s", image.short_id, base)
    try:
        yield image.id
    finally:
        client = image.client
        assert client is not None
        client.images.remove(image.id)


def assert_show_output(
    anylinux_ctr: AnyLinuxContainer,
    wheel: str,
    expected_tag: str,
    strict: bool,
    isa_ext_check: bool = True,
) -> None:
    output = anylinux_ctr.show(wheel, isa_ext_check=isa_ext_check)
    output = output.replace("\n", " ")
    match = SHOW_RE.match(output)
    assert match, f"{SHOW_RE.pattern!r} not found in:\n{output}"
    assert match["wheel"] == wheel
    if strict or "musllinux" in expected_tag:
        assert match["tag"] == expected_tag
    else:
        expected_match = TAG_RE.match(expected_tag)
        assert expected_match, f"No match for tag {expected_tag}"
        expected_glibc = (int(expected_match["major"]), int(expected_match["minor"]))
        actual_match = TAG_RE.match(match["tag"])
        assert actual_match, f"No match for tag {match['tag']}"
        actual_glibc = (int(actual_match["major"]), int(actual_match["minor"]))
        assert expected_match["arch"] == actual_match["arch"]
        assert actual_glibc <= expected_glibc


def build_numpy(container: AnyLinuxContainer, output_dir: Path) -> str:
    """Helper to build numpy from source using the specified container, into
    output_dir."""

    if container.policy.startswith("musllinux_"):
        container.exec("apk add openblas-dev")
        if container.policy.endswith("_s390x"):
            # https://github.com/numpy/numpy/issues/27932
            fix_hwcap = "echo '#define HWCAP_S390_VX 2048' >> /usr/include/bits/hwcap.h"
            container.exec(f'sh -c "{fix_hwcap}"')
    elif container.policy.startswith(("manylinux_2_12_", "manylinux_2_17_")):
        if tuple(int(part) for part in NUMPY_VERSION.split(".")[:2]) >= (1, 26):
            pytest.skip("numpy>=1.26 requires openblas")
        container.exec("yum install -y atlas atlas-devel")
    elif container.policy.startswith(("manylinux_2_31_", "manylinux_2_35_")):
        container.exec("apt-get install -y libopenblas-dev execstack")
        # TODO auditwheel shall check for executable stack:
        # https://github.com/pypa/auditwheel/issues/634
        container.exec(
            ["bash", "-c", "execstack -c $(find /usr/lib* -name 'libopenblas*.so')"]
        )
    else:
        container.exec("dnf install -y openblas-devel")

    cached_wheel = container.cache_dir / ORIGINAL_NUMPY_WHEEL
    orig_wheel = output_dir / ORIGINAL_NUMPY_WHEEL
    if cached_wheel.exists():
        # If numpy has already been built and put in cache, let's reuse this.
        shutil.copy2(cached_wheel, orig_wheel)
    else:
        # otherwise build the original linux_x86_64 numpy wheel from source
        # and put the result in the cache folder to speed-up future build.
        # This part of the build is independent of the auditwheel code-base
        # so it's safe to put it in cache.
        container.exec(f"pip wheel -w /io --no-binary=numpy numpy=={NUMPY_VERSION}")
        cached_wheel.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(orig_wheel, cached_wheel)
    return orig_wheel.name


class Anylinux:
    @pytest.fixture
    def io_folder(self, tmp_path):
        d = tmp_path / "io"
        d.mkdir(exist_ok=True)
        return d

    @pytest.fixture
    def python(
        self, docker_python_img: str, io_folder: Path
    ) -> Generator[PythonContainer, None, None]:
        with docker_container_ctx(docker_python_img, io_folder) as container:
            yield PythonContainer(container)

    @pytest.fixture
    def anylinux(
        self, any_manylinux_img: tuple[str, str], io_folder: Path
    ) -> Generator[AnyLinuxContainer, None, None]:
        policy, manylinux_img = any_manylinux_img
        env = {"PATH": PATH[policy]}
        # coverage is too slow with QEMU, even more so on ppc64le & s390x which lack a
        # C extension.
        # only enable coverage when QEMU is not enabled.
        if os.environ.get("AUDITWHEEL_QEMU", "") != "true":
            env["COVERAGE_PROCESS_START"] = "/auditwheel_src/pyproject.toml"

        with docker_container_ctx(manylinux_img, io_folder, env) as container:
            platform_tag = ".".join(
                sorted(
                    [
                        f"{p}_{PLATFORM}"
                        for p in [policy, *POLICY_ALIASES.get(policy, [])]
                    ]
                )
            )
            yield AnyLinuxContainer(
                f"{policy}_{PLATFORM}", platform_tag, container, io_folder
            )

    def test_numpy(self, anylinux: AnyLinuxContainer, python: PythonContainer) -> None:
        # Integration test: repair numpy built from scratch
        policy = anylinux.policy

        # First build numpy from source as a naive linux wheel that is tied
        # to system libraries (blas, libgfortran...)
        orig_wheel = build_numpy(anylinux, anylinux.io_folder)
        assert orig_wheel == ORIGINAL_NUMPY_WHEEL
        assert "manylinux" not in orig_wheel

        # Repair the wheel using the manylinux container
        anylinux.repair(orig_wheel)
        repaired_wheel = anylinux.check_wheel("numpy", version=NUMPY_VERSION)
        assert_show_output(anylinux, repaired_wheel, policy, False)

        # Check that the repaired numpy wheel can be installed and executed
        # on a modern linux image.
        python.install_wheel(repaired_wheel)
        output = python.run("/auditwheel_src/tests/integration/quick_check_numpy.py")
        assert output.strip() == "ok"

        # Check that numpy f2py works with a more recent version of gfortran
        if policy.startswith("musllinux_"):
            python.exec("apk add musl-dev gfortran")
        else:
            python.exec("apt-get install -y gfortran")
        if tuple(int(part) for part in NUMPY_VERSION.split(".")[:2]) >= (1, 26):
            python.pip_install("meson ninja")
            f2py_env = None
        else:
            f2py_env = {"SETUPTOOLS_USE_DISTUTILS": "stdlib"}
        python.run(
            "-m numpy.f2py -c /auditwheel_src/tests/integration/foo.f90 -m foo",
            env=f2py_env,
        )

        # Check that the 2 fortran runtimes are well isolated and can be loaded
        # at once in the same Python program:
        python.run("import numpy; import foo")

    def test_numpy_sbom(
        self, anylinux: AnyLinuxContainer, python: PythonContainer
    ) -> None:
        policy = anylinux.policy
        if policy.startswith("manylinux_2_12_"):
            pytest.skip(f"whichprovides doesn't support {policy}")

        # Build and repair numpy
        orig_wheel = build_numpy(anylinux, anylinux.io_folder)
        assert orig_wheel == ORIGINAL_NUMPY_WHEEL
        assert "manylinux" not in orig_wheel

        # Repair the wheel using the manylinux container
        anylinux.repair(orig_wheel)
        repaired_wheel = anylinux.check_wheel("numpy", version=NUMPY_VERSION)
        assert_show_output(anylinux, repaired_wheel, policy, False)

        # Install the wheel so the SBOM document is added to the environment.
        python.install_wheel(repaired_wheel)

        # Load the auditwheel SBOM from .dist-info/sboms
        site_packages = python.run(
            "import site; print(site.getsitepackages()[0])"
        ).strip()
        assert re.match(
            r"\A/usr/local/lib/python[0-9.]+/site-packages\Z", site_packages
        )
        sbom_data = python.run(
            f"-c \"print(open('{site_packages}/numpy-{NUMPY_VERSION}.dist-info/sboms/auditwheel.cdx.json').read())\""
        ).strip()
        sbom = json.loads(sbom_data)

        # Separate all the components that vary over test runs.
        sbom_tools = sbom["metadata"].pop("tools")
        sbom_components = sbom.pop("components")
        sbom_dependencies = sbom.pop("dependencies")

        expected_numpy_purl = (
            f"pkg:pypi/numpy@{NUMPY_VERSION}?file_name={repaired_wheel}"
        )
        assert sbom == {
            "bomFormat": "CycloneDX",
            "specVersion": "1.4",
            "version": 1,
            "metadata": {
                "component": {
                    "type": "library",
                    "bom-ref": expected_numpy_purl,
                    "name": "numpy",
                    "version": NUMPY_VERSION,
                    "purl": expected_numpy_purl,
                },
                # "tools": [{...}, ...],
            },
            # "components": [{...}, ...],
            # "dependencies": [{...}, ...],
        }

        assert len(sbom_tools) == 1
        assert sbom_tools[0]["name"] == "auditwheel"
        assert "version" in sbom_tools[0]

        assert sbom_components[0] == {
            "bom-ref": expected_numpy_purl,
            "name": "numpy",
            "purl": expected_numpy_purl,
            "type": "library",
            "version": NUMPY_VERSION,
        }

        component_purls = {
            component["purl"].split("@")[0] for component in sbom_components[1:]
        }
        # Package URL prefixes must match for a policy.
        if policy.startswith("musllinux"):
            expected_purl_prefix = "pkg:apk/alpine/"
        elif policy.startswith("manylinux_2_17_"):
            expected_purl_prefix = "pkg:rpm/centos/"
        elif policy.startswith(("manylinux_2_31_", "manylinux_2_35_")):
            expected_purl_prefix = "pkg:deb/ubuntu/"
        elif policy == "manylinux_2_39_riscv64":
            expected_purl_prefix = "pkg:rpm/rocky/"
        else:
            expected_purl_prefix = "pkg:rpm/almalinux/"

        assert all(purl.startswith(expected_purl_prefix) for purl in component_purls), (
            str(component_purls)
        )

        # We expect libgfortran and openblas* (aka atlas) as dependencies.
        if policy != "musllinux_1_2_riscv64":
            assert any("libgfortran" in purl for purl in component_purls), str(
                component_purls
            )
        assert any("openblas" in purl for purl in component_purls) or any(
            "atlas" in purl for purl in component_purls
        ), str(component_purls)

        assert len(sbom_dependencies) == len(component_purls) + 1

    def test_exclude(self, anylinux: AnyLinuxContainer) -> None:
        """Test the --exclude argument to avoid grafting certain libraries."""
        test_path = "/auditwheel_src/tests/integration/testrpath"
        orig_wheel = anylinux.build_wheel(test_path)

        output = anylinux.repair(
            orig_wheel, excludes=["liba.so"], library_paths=[f"{test_path}/a"]
        )
        assert "Excluding liba.so" in output
        repaired_wheel = anylinux.check_wheel("testrpath")

        # Make sure we don't have liba.so & libb.so in the result
        contents = zipfile.ZipFile(anylinux.io_folder / repaired_wheel).namelist()
        assert not any(x for x in contents if "/liba" in x or "/libb" in x)

    def test_with_binary_executable(
        self, anylinux: AnyLinuxContainer, python: PythonContainer
    ) -> None:
        # Test building a wheel that contains a binary executable (e.g., a program)
        policy = anylinux.policy
        if policy.startswith("musllinux_"):
            anylinux.exec("apk add gsl-dev")
        elif policy.startswith(("manylinux_2_31_", "manylinux_2_35_")):
            anylinux.exec("apt-get install -y libgsl-dev")
        elif policy == "manylinux_2_39_riscv64":
            pytest.skip(reason=f"no gsl-devel on {policy}")
        else:
            anylinux.exec("yum install -y gsl-devel")

        test_path = "/auditwheel_src/tests/integration/testpackage"
        orig_wheel = anylinux.build_wheel(test_path, check_filename=False)
        assert orig_wheel == "testpackage-0.0.1-py3-none-any.whl"

        # manylinux_2_34_x86_64 uses x86_64_v2 for this test
        isa_ext_check = policy != "manylinux_2_34_x86_64"

        # Repair the wheel using the appropriate manylinux container
        anylinux.repair(orig_wheel, isa_ext_check=isa_ext_check)
        repaired_wheel = anylinux.check_wheel("testpackage", python_abi="py3-none")
        assert_show_output(anylinux, repaired_wheel, policy, False, isa_ext_check)

        python.install_wheel(repaired_wheel)
        output = python.run("from testpackage import runit; print(runit(1.5))")
        assert output.strip() == "2.25"

        # Both testprogram and testprogram_nodeps square a number, but:
        #   * testprogram links against libgsl and had to have its RPATH
        #     rewritten.
        #   * testprogram_nodeps links against no shared libraries and wasn't
        #     rewritten.
        #
        # Both executables should work when called from the installed bin directory.
        assert python.exec(["/usr/local/bin/testprogram", "4"]) == "16\n"
        assert python.exec(["/usr/local/bin/testprogram_nodeps", "4"]) == "16\n"

        # testprogram should be a Python shim since we had to rewrite its RPATH.
        shebang = python.exec(["head", "-n1", "/usr/local/bin/testprogram"])
        assert shebang in {
            "#!/usr/local/bin/python\n",
            "#!/usr/local/bin/python3\n",
            f"#!/usr/local/bin/python{'.'.join(PYTHON_MAJ_MIN)}\n",
        }

        # testprogram_nodeps should be the unmodified ELF binary.
        assert (
            python.exec(["head", "-c4", "/usr/local/bin/testprogram_nodeps"])
            == "\x7fELF"
        )

    def test_pure_wheel(self, anylinux: AnyLinuxContainer) -> None:
        anylinux.exec(
            "pip download --no-deps -d /io --only-binary=:all: six==1.16.0",
        )
        orig_wheel = "six-1.16.0-py2.py3-none-any.whl"
        assert anylinux.io_folder.joinpath(orig_wheel).exists()

        # Repair the wheel using the manylinux container
        output = anylinux.repair(orig_wheel, expected_retcode=1)
        assert "This does not look like a platform wheel" in output

        output = anylinux.show(orig_wheel, expected_retcode=1)
        assert "This does not look like a platform wheel" in output

    @pytest.mark.parametrize("dtag", ["rpath", "runpath"])
    def test_rpath(
        self, anylinux: AnyLinuxContainer, python: PythonContainer, dtag: str
    ) -> None:
        # Test building a wheel that contains an extension depending on a library
        # with RPATH or RUNPATH set.
        # Following checks are performed:
        # - check if RUNPATH is replaced by RPATH
        # - check if RPATH location is correct, i.e. it is inside .libs directory
        #   where all gathered libraries are put

        policy = anylinux.policy

        test_path = "/auditwheel_src/tests/integration/testrpath"
        orig_wheel = anylinux.build_wheel(test_path, env={"DTAG": dtag})

        with HERE.joinpath("testrpath", "a", "liba.so").open("rb") as f:
            elf = ELFFile(f)
            dynamic = elf.get_section_by_name(".dynamic")
            tags = {t.entry.d_tag for t in dynamic.iter_tags()}
            assert f"DT_{dtag.upper()}" in tags

        # Repair the wheel using the appropriate manylinux container
        anylinux.repair(orig_wheel, library_paths=[f"{test_path}/a"])
        repaired_wheel = anylinux.check_wheel("testrpath")
        assert_show_output(anylinux, repaired_wheel, policy, False)

        python.install_wheel(repaired_wheel)
        output = python.run("from testrpath import testrpath; print(testrpath.func())")
        assert output.strip() == "11"
        with zipfile.ZipFile(anylinux.io_folder / repaired_wheel) as w:
            libraries = tuple(
                name for name in w.namelist() if "testrpath.libs/lib" in name
            )
            assert len(libraries) == 2
            assert any(".libs/liba" in name for name in libraries)
            for name in libraries:
                with w.open(name) as f:
                    elf = ELFFile(io.BytesIO(f.read()))
                    dynamic = elf.get_section_by_name(".dynamic")
                    assert (
                        len(
                            [
                                t
                                for t in dynamic.iter_tags()
                                if t.entry.d_tag == "DT_RUNPATH"
                            ]
                        )
                        == 0
                    )
                    if ".libs/liba" in name:
                        rpath_tags = [
                            t
                            for t in dynamic.iter_tags()
                            if t.entry.d_tag == "DT_RPATH"
                        ]
                        assert len(rpath_tags) == 1
                        assert rpath_tags[0].rpath == "$ORIGIN"

    def test_multiple_top_level(
        self, anylinux: AnyLinuxContainer, python: PythonContainer
    ) -> None:
        policy = anylinux.policy

        test_path = "/auditwheel_src/tests/integration/multiple_top_level"
        orig_wheel = anylinux.build_wheel(test_path, pre_wheel_cmd="make clean all")

        # Repair the wheel using the appropriate manylinux container
        anylinux.repair(
            orig_wheel,
            library_paths=[f"{test_path}/lib-src/a", f"{test_path}/lib-src/b"],
        )
        repaired_wheel = anylinux.check_wheel("multiple_top_level")
        assert_show_output(anylinux, repaired_wheel, policy, False)

        python.install_wheel(repaired_wheel)
        for mod, func, expected in [
            ("example_a", "example_a", "11"),
            ("example_b", "example_b", "110"),
        ]:
            output = python.run(f"from {mod} import {func}; print({func}())").strip()
            assert output.strip() == expected
        with zipfile.ZipFile(anylinux.io_folder / repaired_wheel) as w:
            for lib_name in ["liba", "libb"]:
                assert any(
                    re.match(rf"multiple_top_level.libs/{lib_name}.*\.so", name)
                    for name in w.namelist()
                )

    def test_internal_rpath(
        self, anylinux: AnyLinuxContainer, python: PythonContainer
    ) -> None:
        policy = anylinux.policy

        test_path = "/auditwheel_src/tests/integration/internal_rpath"
        orig_wheel = anylinux.build_wheel(
            test_path,
            pre_wheel_cmd="make clean all && mv lib-src/a/liba.so internal_rpath",
        )

        # Repair the wheel using the appropriate manylinux container
        anylinux.repair(orig_wheel, library_paths=[f"{test_path}/lib-src/b"])
        repaired_wheel = anylinux.check_wheel("internal_rpath")
        assert_show_output(anylinux, repaired_wheel, policy, False)

        python.install_wheel(repaired_wheel)
        for mod, func, expected in [
            ("example_a", "example_a", "11"),
            ("example_b", "example_b", "10"),
        ]:
            output = python.run(
                f"from internal_rpath.{mod} import {func}; print({func}())"
            )
            assert output.strip() == expected
        with zipfile.ZipFile(anylinux.io_folder / repaired_wheel) as w:
            for lib_name in ["libb"]:
                assert any(
                    re.match(rf"internal_rpath.libs/{lib_name}.*\.so", name)
                    for name in w.namelist()
                )

    def test_strip(self, anylinux: AnyLinuxContainer, python: PythonContainer) -> None:
        policy = anylinux.policy

        test_path = "/auditwheel_src/tests/integration/sample_extension"
        orig_wheel = anylinux.build_wheel(test_path)
        assert orig_wheel.startswith("sample_extension-0.1.0")

        # Repair the wheel using the appropriate manylinux container
        anylinux.repair(orig_wheel, strip=True)

        repaired_wheel = next(anylinux.io_folder.glob(f"*{policy}*.whl")).name

        python.install_wheel(repaired_wheel)
        output = python.run(
            "from sample_extension import test_func; print(test_func(1))"
        )
        assert output.strip() == "2"

    def test_nonpy_rpath(
        self, anylinux: AnyLinuxContainer, python: PythonContainer
    ) -> None:
        # Tests https://github.com/pypa/auditwheel/issues/136
        policy = anylinux.policy

        test_path = "/auditwheel_src/tests/integration/nonpy_rpath"
        orig_wheel = anylinux.build_wheel(test_path)

        # Repair the wheel using the appropriate manylinux container
        anylinux.repair(orig_wheel)
        repaired_wheel = anylinux.check_wheel("nonpy_rpath")
        assert_show_output(anylinux, repaired_wheel, policy, False)

        # Test the resulting wheel outside the manylinux container
        python.install_wheel(repaired_wheel)
        python.run(
            "import nonpy_rpath; assert nonpy_rpath.crypt_something().startswith('*')"
        )

    def test_glibcxx_3_4_25(
        self, anylinux: AnyLinuxContainer, python: PythonContainer
    ) -> None:
        policy = anylinux.policy

        test_path = "/auditwheel_src/tests/integration/test_glibcxx_3_4_25"
        orig_wheel = anylinux.build_wheel(test_path)
        assert orig_wheel.startswith("testentropy-0.0.1")

        # Repair the wheel using the appropriate manylinux container
        if policy.startswith("manylinux_2_28_"):
            with pytest.raises(CalledProcessError):
                anylinux.repair(orig_wheel)
            # TODO if a "permissive" mode is implemented, add the relevant flag to the
            # repair_command here and drop the return statement below
            return

        anylinux.repair(orig_wheel)

        repaired_wheel = next(anylinux.io_folder.glob(f"*{policy}*.whl")).name

        python.install_wheel(repaired_wheel)
        python.run("from testentropy import run; exit(run())")

    @pytest.mark.skipif(
        PLATFORM != "x86_64", reason="ISA extension only implemented on x86_64"
    )
    @pytest.mark.parametrize("isa_ext", ["x86-64-v2", "x86-64-v3", "x86-64-v4"])
    def test_isa_variants(self, anylinux: AnyLinuxContainer, isa_ext: str) -> None:
        policy = anylinux.policy
        if policy.startswith(("manylinux_2_12_", "manylinux_2_17_")):
            pytest.skip("skip old gcc")

        test_path = "/auditwheel_src/tests/integration/testdependencies"
        orig_wheel = anylinux.build_wheel(
            test_path, env={"WITH_DEPENDENCY": "1", "WITH_ARCH": isa_ext}
        )

        # repair failure with ISA check
        with pytest.raises(CalledProcessError):
            anylinux.repair(orig_wheel, library_paths=[test_path])

        anylinux.repair(orig_wheel, library_paths=[test_path], isa_ext_check=False)
        repaired_wheel = anylinux.check_wheel("testdependencies", platform_tag=policy)
        assert_show_output(anylinux, repaired_wheel, policy, True, False)

        # with ISA check, we shall not report a manylinux/musllinux policy
        assert_show_output(anylinux, repaired_wheel, f"linux_{PLATFORM}", True)

    @pytest.mark.parametrize(
        "arch",
        [
            Architecture.aarch64,
            Architecture.armv7l,
            Architecture.i686,
            Architecture.ppc64le,
            Architecture.riscv64,
            Architecture.s390x,
            Architecture.x86_64,
        ],
    )
    @pytest.mark.parametrize("libc", [Libc.GLIBC, Libc.MUSL])
    def test_cross_repair(
        self, anylinux: AnyLinuxContainer, libc: Libc, arch: Architecture
    ) -> None:
        if libc == Libc.MUSL:
            source = "musllinux_1_2"
            platform_tag = f"musllinux_1_2_{arch.value}"
            python_abi = "cp312-cp312"
        else:
            assert libc == Libc.GLIBC
            source = "glibc"
            platform_tag = f"manylinux2014_{arch.value}.manylinux_2_17_{arch.value}"
            if arch in {Architecture.x86_64, Architecture.i686}:
                platform_tag = f"manylinux1_{arch.value}.manylinux_2_5_{arch.value}"
            elif arch == Architecture.riscv64:
                platform_tag = f"manylinux_2_31_{arch.value}"
            python_abi = "cp313-cp313"
        test_path = f"/auditwheel_src/tests/integration/arch-wheels/{source}"
        orig_wheel = f"testsimple-0.0.1-{python_abi}-linux_{arch.value}.whl"
        anylinux.exec(["cp", "-f", f"{test_path}/{orig_wheel}", f"/io/{orig_wheel}"])
        anylinux.repair(orig_wheel, plat="auto", only_plat=False)
        anylinux.check_wheel(
            "testsimple",
            python_abi=python_abi,
            platform_tag=platform_tag,
        )


class TestManylinux(Anylinux):
    @pytest.fixture(scope="session")
    def docker_python_img(self):
        """The glibc Python base image with up-to-date pip"""
        commnds = ["pip install -U pip", "apt-get update -yqq"]
        with tmp_docker_image(MANYLINUX_PYTHON_IMAGE_ID, commnds) as img_id:
            yield img_id

    @pytest.fixture(scope="session", params=MANYLINUX_IMAGES.keys())
    def any_manylinux_img(self, request):
        """Each manylinux image, with auditwheel installed.

        Plus up-to-date pip, setuptools and coverage
        """
        policy = request.param
        check_set = {
            "manylinux_2_12": {"38", "39", "310"},
        }.get(policy)
        if check_set and PYTHON_ABI_MAJ_MIN not in check_set:
            pytest.skip(f"{policy} images do not support cp{PYTHON_ABI_MAJ_MIN}")

        base = MANYLINUX_IMAGES[policy]
        env = {"PATH": PATH[policy]}
        commands = [
            'git config --global --add safe.directory "/auditwheel_src"',
            "pip install -U pip setuptools 'coverage[toml]>=7.13'",
            "pip install -U -e /auditwheel_src",
        ]
        if policy in {"manylinux_2_31", "manylinux_2_35"}:
            commands.append("apt-get update -yqq")
        with tmp_docker_image(base, commands, env) as img_id:
            yield policy, img_id

    @pytest.mark.parametrize("with_dependency", ["0", "1"])
    def test_image_dependencies(
        self, with_dependency: str, anylinux: AnyLinuxContainer, python: PythonContainer
    ) -> None:
        # try to repair the wheel targeting different policies
        #
        # with_dependency == 0
        #   The python module has no dependencies that should be grafted-in and
        #   uses versioned symbols not available on policies pre-dating the policy
        #   matching the image being tested.
        # with_dependency == 1
        #   The python module itself does not use versioned symbols but has a
        #   dependency that should be grafted-in that uses versioned symbols not
        #   available on policies pre-dating the policy matching the image being
        #   tested.

        policy_name = anylinux.policy

        test_path = "/auditwheel_src/tests/integration/testdependencies"
        orig_wheel = anylinux.build_wheel(
            test_path, env={"WITH_DEPENDENCY": with_dependency}
        )

        policies = WheelPolicies(libc=Libc.GLIBC, arch=Architecture(PLATFORM))
        policy = policies.get_policy_by_name(policy_name)
        older_policies = [
            f"{p}_{PLATFORM}"
            for p in MANYLINUX_IMAGES
            if policy < policies.get_policy_by_name(f"{p}_{PLATFORM}")
        ]
        for target_policy in older_policies:
            # we shall fail to repair the wheel when targeting an older policy than
            # the one matching the image
            with pytest.raises(CalledProcessError):
                anylinux.repair(
                    orig_wheel, plat=target_policy, library_paths=[test_path]
                )

        # check all works properly when targeting the policy matching the image
        # use "auto" platform
        anylinux.repair(
            orig_wheel, only_plat=False, plat="auto", library_paths=[test_path]
        )
        repaired_wheel = anylinux.check_wheel("testdependencies")
        # we shall only get the current policy tag with "auto" platform
        assert_show_output(anylinux, repaired_wheel, policy_name, True)

        # check the original wheel with a dependency was not compliant
        # and check the one without a dependency was already compliant
        expected = f"linux_{PLATFORM}" if with_dependency == "1" else policy_name
        assert_show_output(anylinux, orig_wheel, expected, True)

        python.install_wheel(repaired_wheel)
        python.run("from testdependencies import run; exit(run())")

    @pytest.mark.parametrize(
        "target_policy",
        [f"{p}_{PLATFORM}" for p in list(MANYLINUX_IMAGES.keys())]
        + [f"{p}_{PLATFORM}" for aliases in POLICY_ALIASES.values() for p in aliases],
    )
    @pytest.mark.parametrize("only_plat", [True, False])
    def test_compat(
        self,
        target_policy: str,
        only_plat: bool,
        anylinux: AnyLinuxContainer,
        python: PythonContainer,
    ) -> None:
        # test building wheels with compatibility with older spec
        # check aliases for older spec
        test_path = "/auditwheel_src/tests/integration/testsimple"
        orig_wheel = anylinux.build_wheel(test_path)

        if PLATFORM in {"x86_64", "i686"}:
            expect = f"manylinux_2_5_{PLATFORM}"
            expect_tag = f"manylinux1_{PLATFORM}.manylinux_2_5_{PLATFORM}"
        elif PLATFORM == "riscv64":
            expect = f"manylinux_2_31_{PLATFORM}"
            expect_tag = f"manylinux_2_31_{PLATFORM}"
        else:
            expect = f"manylinux_2_17_{PLATFORM}"
            expect_tag = f"manylinux2014_{PLATFORM}.manylinux_2_17_{PLATFORM}"

        target_tag = target_policy
        for pep600_policy, aliases in POLICY_ALIASES.items():
            policy_ = f"{pep600_policy}_{PLATFORM}"
            aliases_ = [f"{p}_{PLATFORM}" for p in aliases]
            if target_policy == policy_ or target_policy in aliases_:
                target_tag = ".".join(sorted([policy_, *aliases_]))

        # we shall ba able to repair the wheel for all targets
        anylinux.repair(orig_wheel, plat=target_policy, only_plat=only_plat)
        if only_plat or target_tag == expect_tag:
            repaired_tag = target_tag
        else:
            repaired_tag = ".".join(
                sorted(expect_tag.split(".") + target_tag.split("."))
            )
        repaired_wheel = anylinux.check_wheel("testsimple", platform_tag=repaired_tag)

        assert_show_output(anylinux, repaired_wheel, expect, True)

        with zipfile.ZipFile(anylinux.io_folder / repaired_wheel) as z:
            for file in z.namelist():
                assert not file.startswith("testsimple.libs"), (
                    "should not have empty .libs folder"
                )

        python.install_wheel(repaired_wheel)
        python.run("from testsimple import run; exit(run())")

    @pytest.mark.skipif(
        PLATFORM != "x86_64", reason=f"libmvec not supported on {PLATFORM}"
    )
    def test_mvec(self, anylinux: AnyLinuxContainer, python: PythonContainer) -> None:
        # Tests https://github.com/pypa/auditwheel/issues/645
        policy = anylinux.policy

        if policy.startswith(("manylinux_2_12_", "manylinux_2_17_")):
            pytest.skip(f"libmvec not supported on {policy}")

        test_path = "/auditwheel_src/tests/integration/test_mvec"
        orig_wheel = anylinux.build_wheel(test_path, check_filename=False)

        # Repair the wheel using the appropriate manylinux container
        anylinux.repair(orig_wheel, only_plat=False)
        platform_tag = f"manylinux_2_24_x86_64.{policy}"
        repaired_wheel = anylinux.check_wheel(
            "test_mvec", python_abi="py3-none", platform_tag=platform_tag
        )
        assert_show_output(anylinux, repaired_wheel, policy, False)

        # Test the resulting wheel outside the manylinux container
        python.install_wheel(repaired_wheel)

    def test_zlib_blacklist(self, anylinux: AnyLinuxContainer) -> None:
        policy = anylinux.policy
        if policy.startswith(
            (
                "manylinux_2_17_",
                "manylinux_2_28_",
                "manylinux_2_31_",
                "manylinux_2_34_",
                "manylinux_2_35_",
                "manylinux_2_39_",
            )
        ):
            pytest.skip(f"{policy} image has no blacklist symbols in libz.so.1")

        test_path = "/auditwheel_src/tests/integration/testzlib"
        orig_wheel = anylinux.build_wheel(test_path)
        assert orig_wheel.startswith("testzlib-0.0.1")

        # Repair the wheel using the appropriate manylinux container
        with pytest.raises(CalledProcessError):
            anylinux.repair(orig_wheel)

        # Check auditwheel show warns about the black listed symbols
        output = anylinux.show(orig_wheel, verbose=True)
        assert "black-listed symbol dependencies" in output.replace("\n", " ")


class TestMusllinux(Anylinux):
    @pytest.fixture(scope="session")
    def docker_python_img(self):
        """The alpine Python base image with up-to-date pip"""
        commands = ["pip install -U pip"]
        with tmp_docker_image(MUSLLINUX_PYTHON_IMAGE_ID, commands) as img_id:
            yield img_id

    @pytest.fixture(scope="session", params=MUSLLINUX_IMAGES.keys())
    def any_manylinux_img(self, request):
        """Each musllinux image, with auditwheel installed.

        Plus up-to-date pip, setuptools and coverage
        """
        policy = request.param
        base = MUSLLINUX_IMAGES[policy]
        env = {"PATH": PATH[policy]}
        commands = [
            'git config --global --add safe.directory "/auditwheel_src"',
            "pip install -U pip setuptools 'coverage[toml]>=7.13'",
            "pip install -U -e /auditwheel_src",
        ]
        with tmp_docker_image(base, commands, env) as img_id:
            yield policy, img_id
