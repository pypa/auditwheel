from __future__ import annotations

import glob
import io
import logging
import os
import os.path as op
import re
import shutil
import sys
import zipfile
from contextlib import contextmanager
from subprocess import CalledProcessError

import docker
import pytest
from elftools.elf.elffile import ELFFile

from auditwheel.architecture import Architecture
from auditwheel.policy import WheelPolicies

logger = logging.getLogger(__name__)

ENCODING = "utf-8"
PLATFORM = Architecture.get_native_architecture().value
MANYLINUX1_IMAGE_ID = f"quay.io/pypa/manylinux1_{PLATFORM}:latest"
MANYLINUX2010_IMAGE_ID = f"quay.io/pypa/manylinux2010_{PLATFORM}:latest"
MANYLINUX2014_IMAGE_ID = f"quay.io/pypa/manylinux2014_{PLATFORM}:latest"
MANYLINUX_2_28_IMAGE_ID = f"quay.io/pypa/manylinux_2_28_{PLATFORM}:latest"
MANYLINUX_2_34_IMAGE_ID = f"quay.io/pypa/manylinux_2_34_{PLATFORM}:latest"
if PLATFORM in {"i686", "x86_64"}:
    MANYLINUX_IMAGES = {
        "manylinux_2_5": MANYLINUX1_IMAGE_ID,
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
else:
    MANYLINUX_IMAGES = {
        "manylinux_2_17": MANYLINUX2014_IMAGE_ID,
        "manylinux_2_28": MANYLINUX_2_28_IMAGE_ID,
        "manylinux_2_34": MANYLINUX_2_34_IMAGE_ID,
    }
    POLICY_ALIASES = {
        "manylinux_2_17": ["manylinux2014"],
    }
DOCKER_CONTAINER_NAME = "auditwheel-test-anylinux"
PYTHON_MAJ_MIN = [str(i) for i in sys.version_info[:2]]
PYTHON_ABI_MAJ_MIN = "".join(PYTHON_MAJ_MIN)
PYTHON_ABI = f"cp{PYTHON_ABI_MAJ_MIN}-cp{PYTHON_ABI_MAJ_MIN}"
PYTHON_IMAGE_TAG = ".".join(PYTHON_MAJ_MIN)
MANYLINUX_PYTHON_IMAGE_ID = f"python:{PYTHON_IMAGE_TAG}-slim-bookworm"
MUSLLINUX_IMAGES = {
    "musllinux_1_2": f"quay.io/pypa/musllinux_1_2_{PLATFORM}:latest",
}
MUSLLINUX_PYTHON_IMAGE_ID = f"python:{PYTHON_IMAGE_TAG}-alpine"
DEVTOOLSET = {
    "manylinux_2_5": "devtoolset-2",
    "manylinux_2_12": "devtoolset-8",
    "manylinux_2_17": "devtoolset-10",
    "manylinux_2_28": "gcc-toolset-14",
    "manylinux_2_34": "gcc-toolset-14",
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
WHEEL_CACHE_FOLDER = op.expanduser("~/.cache/auditwheel_tests")
NUMPY_VERSION_MAP = {
    "39": "1.21.4",
    "310": "1.21.4",
    "311": "1.23.4",
    "312": "1.26.0",
    "313": "2.0.1",
}
NUMPY_VERSION = NUMPY_VERSION_MAP[PYTHON_ABI_MAJ_MIN]
ORIGINAL_NUMPY_WHEEL = f"numpy-{NUMPY_VERSION}-{PYTHON_ABI}-linux_{PLATFORM}.whl"
SHOW_RE = re.compile(
    r'.*[\s](?P<wheel>\S+) is consistent with the following platform tag: "(?P<tag>\S+)".*',
    flags=re.DOTALL,
)
TAG_RE = re.compile(r"^manylinux_(?P<major>[0-9]+)_(?P<minor>[0-9]+)_(?P<arch>\S+)$")


def find_src_folder():
    candidate = op.abspath(op.join(op.dirname(__file__), "../.."))
    contents = os.listdir(candidate)
    if "setup.py" in contents and "src" in contents:
        return candidate
    return None


def docker_start(image, volumes=None, env_variables=None):
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

    logger.info("Starting container with image %r", image)
    con = client.containers.run(
        image,
        ["sleep", "10000"],
        detach=True,
        volumes=dvolumes,
        environment=env_variables,
    )
    logger.info("Started container %s", con.id[:12])
    return con


@contextmanager
def docker_container_ctx(image, io_dir=None, env_variables=None):
    if env_variables is None:
        env_variables = {}
    src_folder = find_src_folder()
    if src_folder is None:
        pytest.skip("Can only be run from the source folder")
    vols = {"/auditwheel_src": src_folder}
    if io_dir is not None:
        vols["/io"] = io_dir

    for key in env_variables:
        if key.startswith("COV_CORE_"):
            env_variables[key] = env_variables[key].replace(
                src_folder, "/auditwheel_src"
            )

    container = docker_start(image, vols, env_variables)
    try:
        yield container
    finally:
        container.remove(force=True)


def docker_exec(container, cmd, expected_retcode=0):
    logger.info("docker exec %s: %r", container.id[:12], cmd)
    ec, output = container.exec_run(cmd)
    output = output.decode(ENCODING)
    if ec != expected_retcode:
        print(output)
        raise CalledProcessError(ec, cmd, output=output)
    return output


@contextmanager
def tmp_docker_image(base, commands, setup_env=None):
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
        client.images.remove(image.id)


def assert_show_output(manylinux_ctr, wheel, expected_tag, strict, isa_ext_check=True):
    isa_ext_check_arg = "" if isa_ext_check else "--disable-isa-ext-check"
    output = docker_exec(
        manylinux_ctr, f"auditwheel show {isa_ext_check_arg} /io/{wheel}"
    )
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


def build_numpy(container, policy, output_dir):
    """Helper to build numpy from source using the specified container, into
    output_dir."""

    if policy.startswith("musllinux_"):
        docker_exec(container, "apk add openblas-dev")
        if policy.endswith("_s390x"):
            # https://github.com/numpy/numpy/issues/27932
            fix_hwcap = "echo '#define HWCAP_S390_VX 2048' >> /usr/include/bits/hwcap.h"
            docker_exec(container, f'sh -c "{fix_hwcap}"')
    elif policy.startswith(("manylinux_2_28_", "manylinux_2_34_")):
        docker_exec(container, "dnf install -y openblas-devel")
    else:
        if tuple(int(part) for part in NUMPY_VERSION.split(".")[:2]) >= (1, 26):
            pytest.skip("numpy>=1.26 requires openblas")
        docker_exec(container, "yum install -y atlas atlas-devel")

    if op.exists(op.join(WHEEL_CACHE_FOLDER, policy, ORIGINAL_NUMPY_WHEEL)):
        # If numpy has already been built and put in cache, let's reuse this.
        shutil.copy2(
            op.join(WHEEL_CACHE_FOLDER, policy, ORIGINAL_NUMPY_WHEEL),
            op.join(output_dir, ORIGINAL_NUMPY_WHEEL),
        )
    else:
        # otherwise build the original linux_x86_64 numpy wheel from source
        # and put the result in the cache folder to speed-up future build.
        # This part of the build is independent of the auditwheel code-base
        # so it's safe to put it in cache.

        docker_exec(
            container,
            f"pip wheel -w /io --no-binary=numpy numpy=={NUMPY_VERSION}",
        )
        os.makedirs(op.join(WHEEL_CACHE_FOLDER, policy), exist_ok=True)
        shutil.copy2(
            op.join(output_dir, ORIGINAL_NUMPY_WHEEL),
            op.join(WHEEL_CACHE_FOLDER, policy, ORIGINAL_NUMPY_WHEEL),
        )
    orig_wheel, *_ = os.listdir(output_dir)
    return orig_wheel


class Anylinux:
    @pytest.fixture
    def io_folder(self, tmp_path):
        d = tmp_path / "io"
        d.mkdir(exist_ok=True)
        return str(d)

    @pytest.fixture
    def docker_python(self, docker_python_img, io_folder):
        with docker_container_ctx(docker_python_img, io_folder) as container:
            yield container

    @pytest.fixture
    def any_manylinux_container(self, any_manylinux_img, io_folder):
        policy, manylinux_img = any_manylinux_img
        env = {"PATH": PATH[policy]}
        for key in os.environ:
            if key.startswith("COV_CORE_"):
                env[key] = os.environ[key]

        with docker_container_ctx(manylinux_img, io_folder, env) as container:
            platform_tag = ".".join(
                [f"{p}_{PLATFORM}" for p in [policy, *POLICY_ALIASES.get(policy, [])]]
            )
            yield f"{policy}_{PLATFORM}", platform_tag, container

    def test_build_repair_numpy(
        self, any_manylinux_container, docker_python, io_folder
    ):
        # Integration test: repair numpy built from scratch
        policy, tag, manylinux_ctr = any_manylinux_container

        # First build numpy from source as a naive linux wheel that is tied
        # to system libraries (blas, libgfortran...)
        orig_wheel = build_numpy(manylinux_ctr, policy, io_folder)
        assert orig_wheel == ORIGINAL_NUMPY_WHEEL
        assert "manylinux" not in orig_wheel

        # Repair the wheel using the manylinux container
        repair_command = (
            f"auditwheel repair --plat {policy} --only-plat -w /io /io/{orig_wheel}"
        )
        docker_exec(manylinux_ctr, repair_command)
        filenames = os.listdir(io_folder)
        assert len(filenames) == 2
        repaired_wheel = f"numpy-{NUMPY_VERSION}-{PYTHON_ABI}-{tag}.whl"
        assert repaired_wheel in filenames
        assert_show_output(manylinux_ctr, repaired_wheel, policy, False)

        # Check that the repaired numpy wheel can be installed and executed
        # on a modern linux image.
        docker_exec(docker_python, "pip install /io/" + repaired_wheel)
        output = docker_exec(
            docker_python,
            "python /auditwheel_src/tests/integration/quick_check_numpy.py",
        )
        assert output.strip() == "ok"

        # Check that numpy f2py works with a more recent version of gfortran
        if policy.startswith("musllinux_"):
            docker_exec(docker_python, "apk add musl-dev gfortran")
        else:
            docker_exec(docker_python, "apt-get update -yqq")
            docker_exec(docker_python, "apt-get install -y gfortran")
        if tuple(int(part) for part in NUMPY_VERSION.split(".")[:2]) >= (1, 26):
            docker_exec(docker_python, "pip install meson ninja")
        docker_exec(
            docker_python,
            "python -m numpy.f2py -c /auditwheel_src/tests/integration/foo.f90 -m foo",
        )

        # Check that the 2 fortran runtimes are well isolated and can be loaded
        # at once in the same Python program:
        docker_exec(docker_python, ["python", "-c", "'import numpy; import foo'"])

    def test_repair_exclude(self, any_manylinux_container, io_folder):
        """Test the --exclude argument to avoid grafting certain libraries."""

        policy, tag, manylinux_ctr = any_manylinux_container

        test_path = "/auditwheel_src/tests/integration/testrpath"
        build_cmd = (
            f"cd {test_path} && "
            "if [ -d ./build ]; then rm -rf ./build ./*.egg-info; fi && "
            "python -m pip wheel --no-deps -w /io ."
        )
        docker_exec(manylinux_ctr, ["bash", "-c", build_cmd])
        filenames = os.listdir(io_folder)
        assert filenames == [f"testrpath-0.0.1-{PYTHON_ABI}-linux_{PLATFORM}.whl"]
        orig_wheel = filenames[0]
        assert "manylinux" not in orig_wheel

        repair_command = [
            f"LD_LIBRARY_PATH={test_path}/a:$LD_LIBRARY_PATH",
            "auditwheel",
            "repair",
            f"--plat={policy}",
            "--only-plat",
            "-w",
            "/io",
            "--exclude=liba.so",
            f"/io/{orig_wheel}",
        ]
        output = docker_exec(manylinux_ctr, ["bash", "-c", " ".join(repair_command)])
        assert "Excluding liba.so" in output
        filenames = os.listdir(io_folder)
        assert len(filenames) == 2
        repaired_wheel = f"testrpath-0.0.1-{PYTHON_ABI}-{tag}.whl"
        assert repaired_wheel in filenames

        # Make sure we don't have liba.so & libb.so in the result
        contents = zipfile.ZipFile(os.path.join(io_folder, repaired_wheel)).namelist()
        assert not any(x for x in contents if "/liba" in x or "/libb" in x)

    def test_build_wheel_with_binary_executable(
        self, any_manylinux_container, docker_python, io_folder
    ):
        # Test building a wheel that contains a binary executable (e.g., a program)

        policy, tag, manylinux_ctr = any_manylinux_container
        if policy.startswith("musllinux_"):
            docker_exec(manylinux_ctr, "apk add gsl-dev")
        else:
            docker_exec(manylinux_ctr, "yum install -y gsl-devel")

        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                "cd /auditwheel_src/tests/integration/testpackage && "
                "if [ -d ./build ]; then rm -rf ./build ./*.egg-info; fi && "
                "python -m pip wheel --no-deps -w /io .",
            ],
        )

        filenames = os.listdir(io_folder)
        assert filenames == ["testpackage-0.0.1-py3-none-any.whl"]
        orig_wheel = filenames[0]
        assert "manylinux" not in orig_wheel

        # manylinux_2_34_x86_64 uses x86_64_v2 for this test
        isa_ext_check = policy != "manylinux_2_34_x86_64"
        isa_ext_check_arg = "" if isa_ext_check else "--disable-isa-ext-check"

        # Repair the wheel using the appropriate manylinux container
        repair_command = f"auditwheel repair --plat {policy} {isa_ext_check_arg} --only-plat -w /io /io/{orig_wheel}"
        docker_exec(manylinux_ctr, repair_command)
        filenames = os.listdir(io_folder)
        assert len(filenames) == 2
        repaired_wheel = f"testpackage-0.0.1-py3-none-{tag}.whl"
        assert repaired_wheel in filenames
        assert_show_output(manylinux_ctr, repaired_wheel, policy, False, isa_ext_check)

        docker_exec(docker_python, "pip install /io/" + repaired_wheel)
        output = docker_exec(
            docker_python,
            ["python", "-c", "from testpackage import runit; print(runit(1.5))"],
        )
        assert output.strip() == "2.25"

        # Both testprogram and testprogram_nodeps square a number, but:
        #   * testprogram links against libgsl and had to have its RPATH
        #     rewritten.
        #   * testprogram_nodeps links against no shared libraries and wasn't
        #     rewritten.
        #
        # Both executables should work when called from the installed bin directory.
        assert docker_exec(docker_python, ["/usr/local/bin/testprogram", "4"]) == "16\n"
        assert (
            docker_exec(docker_python, ["/usr/local/bin/testprogram_nodeps", "4"])
            == "16\n"
        )

        # testprogram should be a Python shim since we had to rewrite its RPATH.
        shebang = docker_exec(
            docker_python, ["head", "-n1", "/usr/local/bin/testprogram"]
        )
        assert shebang in {
            "#!/usr/local/bin/python\n",
            "#!/usr/local/bin/python3\n",
            f"#!/usr/local/bin/python{'.'.join(PYTHON_MAJ_MIN)}\n",
        }

        # testprogram_nodeps should be the unmodified ELF binary.
        assert (
            docker_exec(
                docker_python, ["head", "-c4", "/usr/local/bin/testprogram_nodeps"]
            )
            == "\x7fELF"
        )

    def test_build_repair_pure_wheel(self, any_manylinux_container, io_folder):
        policy, tag, manylinux_ctr = any_manylinux_container

        docker_exec(
            manylinux_ctr,
            "pip download --no-deps -d /io --only-binary=:all: six==1.16.0",
        )

        filenames = os.listdir(io_folder)
        assert filenames == ["six-1.16.0-py2.py3-none-any.whl"]
        orig_wheel = filenames[0]
        assert "manylinux" not in orig_wheel

        # Repair the wheel using the manylinux container
        repair_command = f"auditwheel repair --plat {policy} -w /io /io/{orig_wheel}"
        output = docker_exec(manylinux_ctr, repair_command, expected_retcode=1)
        assert "This does not look like a platform wheel" in output

        output = docker_exec(
            manylinux_ctr, f"auditwheel show /io/{orig_wheel}", expected_retcode=1
        )
        assert "This does not look like a platform wheel" in output

    @pytest.mark.parametrize("dtag", ["rpath", "runpath"])
    def test_build_wheel_depending_on_library_with_rpath(
        self, any_manylinux_container, docker_python, io_folder, dtag
    ):
        # Test building a wheel that contains an extension depending on a library
        # with RPATH or RUNPATH set.
        # Following checks are performed:
        # - check if RUNPATH is replaced by RPATH
        # - check if RPATH location is correct, i.e. it is inside .libs directory
        #   where all gathered libraries are put

        policy, tag, manylinux_ctr = any_manylinux_container

        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                (
                    "cd /auditwheel_src/tests/integration/testrpath &&"
                    "if [ -d ./build ]; then rm -rf ./build ./*.egg-info; fi && "
                    f"DTAG={dtag} python -m pip wheel --no-deps -w /io ."
                ),
            ],
        )
        with open(
            op.join(op.dirname(__file__), "testrpath", "a", "liba.so"), "rb"
        ) as f:
            elf = ELFFile(f)
            dynamic = elf.get_section_by_name(".dynamic")
            tags = {t.entry.d_tag for t in dynamic.iter_tags()}
            assert f"DT_{dtag.upper()}" in tags
        filenames = os.listdir(io_folder)
        assert filenames == [f"testrpath-0.0.1-{PYTHON_ABI}-linux_{PLATFORM}.whl"]
        orig_wheel = filenames[0]
        assert "manylinux" not in orig_wheel

        # Repair the wheel using the appropriate manylinux container
        repair_command = (
            f"auditwheel repair --plat {policy} --only-plat -w /io /io/{orig_wheel}"
        )
        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                "LD_LIBRARY_PATH="
                "/auditwheel_src/tests/integration/testrpath/a:$LD_LIBRARY_PATH "
                + repair_command,
            ],
        )
        filenames = os.listdir(io_folder)
        assert len(filenames) == 2
        repaired_wheel = f"testrpath-0.0.1-{PYTHON_ABI}-{tag}.whl"
        assert repaired_wheel in filenames
        assert_show_output(manylinux_ctr, repaired_wheel, policy, False)

        docker_exec(docker_python, "pip install /io/" + repaired_wheel)
        output = docker_exec(
            docker_python,
            [
                "python",
                "-c",
                "from testrpath import testrpath; print(testrpath.func())",
            ],
        )
        assert output.strip() == "11"
        with zipfile.ZipFile(os.path.join(io_folder, repaired_wheel)) as w:
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

    def test_build_repair_multiple_top_level_modules_wheel(
        self, any_manylinux_container, docker_python, io_folder
    ):
        policy, tag, manylinux_ctr = any_manylinux_container

        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                "cd /auditwheel_src/tests/integration/multiple_top_level && "
                "if [ -d ./build ]; then rm -rf ./build ./*.egg-info; fi && "
                "make clean all && "
                "pip wheel . -w /io",
            ],
        )

        filenames = os.listdir(io_folder)
        assert filenames == [
            f"multiple_top_level-1.0-{PYTHON_ABI}-linux_{PLATFORM}.whl"
        ]
        orig_wheel = filenames[0]
        assert "manylinux" not in orig_wheel

        # Repair the wheel using the appropriate manylinux container
        repair_command = (
            f"auditwheel repair --plat {policy} --only-plat -w /io /io/{orig_wheel}"
        )
        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                (
                    "LD_LIBRARY_PATH="
                    "/auditwheel_src/tests/integration/multiple_top_level/lib-src/a:"
                    "/auditwheel_src/tests/integration/multiple_top_level/lib-src/b:"
                    "$LD_LIBRARY_PATH "
                )
                + repair_command,
            ],
        )
        filenames = os.listdir(io_folder)
        assert len(filenames) == 2
        repaired_wheel = f"multiple_top_level-1.0-{PYTHON_ABI}-{tag}.whl"
        assert repaired_wheel in filenames
        assert_show_output(manylinux_ctr, repaired_wheel, policy, False)

        docker_exec(docker_python, "pip install /io/" + repaired_wheel)
        for mod, func, expected in [
            ("example_a", "example_a", "11"),
            ("example_b", "example_b", "110"),
        ]:
            output = docker_exec(
                docker_python,
                [
                    "python",
                    "-c",
                    f"from {mod} import {func}; print({func}())",
                ],
            ).strip()
            assert output.strip() == expected
        with zipfile.ZipFile(os.path.join(io_folder, repaired_wheel)) as w:
            for lib_name in ["liba", "libb"]:
                assert any(
                    re.match(rf"multiple_top_level.libs/{lib_name}.*\.so", name)
                    for name in w.namelist()
                )

    def test_build_repair_wheel_with_internal_rpath(
        self, any_manylinux_container, docker_python, io_folder
    ):
        policy, tag, manylinux_ctr = any_manylinux_container

        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                "cd /auditwheel_src/tests/integration/internal_rpath && "
                "if [ -d ./build ]; then rm -rf ./build ./*.egg-info; fi && "
                "make clean all && "
                "mv lib-src/a/liba.so internal_rpath && "
                "pip wheel . -w /io",
            ],
        )

        filenames = os.listdir(io_folder)
        assert filenames == [f"internal_rpath-1.0-{PYTHON_ABI}-linux_{PLATFORM}.whl"]
        orig_wheel = filenames[0]
        assert "manylinux" not in orig_wheel

        # Repair the wheel using the appropriate manylinux container
        repair_command = (
            f"auditwheel repair --plat {policy} --only-plat -w /io /io/{orig_wheel}"
        )
        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                (
                    "LD_LIBRARY_PATH="
                    "/auditwheel_src/tests/integration/internal_rpath/lib-src/b:"
                    "$LD_LIBRARY_PATH "
                )
                + repair_command,
            ],
        )
        filenames = os.listdir(io_folder)
        assert len(filenames) == 2
        repaired_wheel = f"internal_rpath-1.0-{PYTHON_ABI}-{tag}.whl"
        assert repaired_wheel in filenames
        assert_show_output(manylinux_ctr, repaired_wheel, policy, False)

        docker_exec(docker_python, "pip install /io/" + repaired_wheel)
        for mod, func, expected in [
            ("example_a", "example_a", "11"),
            ("example_b", "example_b", "10"),
        ]:
            output = docker_exec(
                docker_python,
                [
                    "python",
                    "-c",
                    f"from internal_rpath.{mod} import {func}; print({func}())",
                ],
            ).strip()
            assert output.strip() == expected
        with zipfile.ZipFile(os.path.join(io_folder, repaired_wheel)) as w:
            for lib_name in ["libb"]:
                assert any(
                    re.match(rf"internal_rpath.libs/{lib_name}.*\.so", name)
                    for name in w.namelist()
                )

    def test_strip_wheel(self, any_manylinux_container, docker_python, io_folder):
        policy, tag, manylinux_ctr = any_manylinux_container
        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                "cd /auditwheel_src/tests/integration/sample_extension && "
                "if [ -d ./build ]; then rm -rf ./build ./*.egg-info; fi && "
                "python -m pip wheel --no-deps -w /io .",
            ],
        )

        orig_wheel, *_ = os.listdir(io_folder)
        assert orig_wheel.startswith("sample_extension-0.1.0")

        # Repair the wheel using the appropriate manylinux container
        repair_command = (
            f"auditwheel repair --plat {policy} --strip -w /io /io/{orig_wheel}"
        )
        docker_exec(manylinux_ctr, repair_command)

        repaired_wheel, *_ = glob.glob(f"{io_folder}/*{policy}*.whl")
        repaired_wheel = os.path.basename(repaired_wheel)

        docker_exec(docker_python, "pip install /io/" + repaired_wheel)
        output = docker_exec(
            docker_python,
            [
                "python",
                "-c",
                "from sample_extension import test_func; print(test_func(1))",
            ],
        )
        assert output.strip() == "2"

    def test_nonpy_rpath(self, any_manylinux_container, docker_python, io_folder):
        # Tests https://github.com/pypa/auditwheel/issues/136
        policy, tag, manylinux_ctr = any_manylinux_container
        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                "cd /auditwheel_src/tests/integration/nonpy_rpath && "
                "if [ -d ./build ]; then rm -rf ./build ./*.egg-info; fi && "
                "python -m pip wheel --no-deps -w /io .",
            ],
        )

        orig_wheel, *_ = os.listdir(io_folder)
        assert orig_wheel.startswith("nonpy_rpath-0.1.0")
        assert "manylinux" not in orig_wheel

        # Repair the wheel using the appropriate manylinux container
        repair_command = (
            f"auditwheel repair --plat {policy} --only-plat -w /io /io/{orig_wheel}"
        )
        docker_exec(manylinux_ctr, ["bash", "-c", repair_command])
        filenames = os.listdir(io_folder)
        assert len(filenames) == 2
        repaired_wheel = f"nonpy_rpath-0.1.0-{PYTHON_ABI}-{tag}.whl"
        assert repaired_wheel in filenames
        assert_show_output(manylinux_ctr, repaired_wheel, policy, False)

        # Test the resulting wheel outside the manylinux container
        docker_exec(docker_python, "pip install /io/" + repaired_wheel)
        docker_exec(
            docker_python,
            [
                "python",
                "-c",
                "import nonpy_rpath\n"
                "assert nonpy_rpath.crypt_something().startswith('*')",
            ],
        )

    def test_glibcxx_3_4_25(self, any_manylinux_container, docker_python, io_folder):
        policy, tag, manylinux_ctr = any_manylinux_container
        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                "cd /auditwheel_src/tests/integration/test_glibcxx_3_4_25 && "
                "if [ -d ./build ]; then rm -rf ./build ./*.egg-info; fi && "
                "python -m pip wheel --no-deps -w /io .",
            ],
        )

        orig_wheel, *_ = os.listdir(io_folder)
        assert orig_wheel.startswith("testentropy-0.0.1")

        # Repair the wheel using the appropriate manylinux container
        repair_command = f"auditwheel repair --plat {policy} -w /io /io/{orig_wheel}"
        if policy.startswith("manylinux_2_28_"):
            with pytest.raises(CalledProcessError):
                docker_exec(manylinux_ctr, repair_command)
            # TODO if a "permissive" mode is implemented, add the relevant flag to the
            # repair_command here and drop the return statement below
            return

        docker_exec(manylinux_ctr, repair_command)

        repaired_wheel, *_ = glob.glob(f"{io_folder}/*{policy}*.whl")
        repaired_wheel = os.path.basename(repaired_wheel)

        docker_exec(docker_python, "pip install /io/" + repaired_wheel)
        docker_exec(
            docker_python,
            [
                "python",
                "-c",
                "from testentropy import run; exit(run())",
            ],
        )

    @pytest.mark.skipif(
        PLATFORM != "x86_64", reason="ISA extension only implemented on x86_64"
    )
    @pytest.mark.parametrize("isa_ext", ["x86-64-v2", "x86-64-v3", "x86-64-v4"])
    def test_isa_variants(self, any_manylinux_container, io_folder, isa_ext):
        policy, tag, manylinux_ctr = any_manylinux_container
        if policy.startswith(("manylinux_2_5_", "manylinux_2_12_", "manylinux_2_17_")):
            pytest.skip("skip old gcc")
        build_command = (
            "cd /auditwheel_src/tests/integration/testdependencies && "
            "if [ -d ./build ]; then rm -rf ./build ./*.egg-info; fi && "
            f"WITH_DEPENDENCY=1 WITH_ARCH={isa_ext} python -m pip wheel --no-deps -w /io ."
        )
        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                build_command,
            ],
        )

        filenames = os.listdir(io_folder)
        orig_wheel = filenames[0]
        assert "manylinux" not in orig_wheel

        # repair failure with ISA check
        repair_command = (
            "LD_LIBRARY_PATH="
            "/auditwheel_src/tests/integration/testdependencies:$LD_LIBRARY_PATH "
            f"auditwheel repair --plat {policy} -w /io /io/{orig_wheel}"
        )
        with pytest.raises(CalledProcessError):
            docker_exec(manylinux_ctr, ["bash", "-c", repair_command])

        repair_command = (
            "LD_LIBRARY_PATH="
            "/auditwheel_src/tests/integration/testdependencies:$LD_LIBRARY_PATH "
            f"auditwheel repair --disable-isa-ext-check --plat {policy} -w /io /io/{orig_wheel}"
        )
        docker_exec(manylinux_ctr, ["bash", "-c", repair_command])

        filenames = os.listdir(io_folder)
        assert len(filenames) == 2
        repaired_wheel = f"testdependencies-0.0.1-{PYTHON_ABI}-{policy}.whl"
        assert repaired_wheel in filenames
        assert_show_output(manylinux_ctr, repaired_wheel, policy, True, False)

        # with ISA check, we shall not report a manylinux/musllinux policy
        assert_show_output(manylinux_ctr, repaired_wheel, f"linux_{PLATFORM}", True)


class TestManylinux(Anylinux):
    @pytest.fixture(scope="session")
    def docker_python_img(self):
        """The glibc Python base image with up-to-date pip"""
        with tmp_docker_image(
            MANYLINUX_PYTHON_IMAGE_ID, ["pip install -U pip"]
        ) as img_id:
            yield img_id

    @pytest.fixture(scope="session", params=MANYLINUX_IMAGES.keys())
    def any_manylinux_img(self, request):
        """Each manylinux image, with auditwheel installed.

        Plus up-to-date pip, setuptools and pytest-cov
        """
        policy = request.param
        support_check_map = {
            "manylinux_2_5": {"38", "39"},
            "manylinux_2_12": {"38", "39", "310"},
        }
        check_set = support_check_map.get(policy)
        if check_set and PYTHON_ABI_MAJ_MIN not in check_set:
            pytest.skip(f"{policy} images do not support cp{PYTHON_ABI_MAJ_MIN}")

        base = MANYLINUX_IMAGES[policy]
        env = {"PATH": PATH[policy]}
        with tmp_docker_image(
            base,
            [
                'git config --global --add safe.directory "/auditwheel_src"',
                "pip install -U pip setuptools pytest-cov",
                "pip install -U -e /auditwheel_src",
            ],
            env,
        ) as img_id:
            yield policy, img_id

    @pytest.mark.parametrize("with_dependency", ["0", "1"])
    def test_build_wheel_with_image_dependencies(
        self, with_dependency, any_manylinux_container, docker_python, io_folder
    ):
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

        policy, tag, manylinux_ctr = any_manylinux_container
        build_command = (
            "cd /auditwheel_src/tests/integration/testdependencies && "
            "if [ -d ./build ]; then rm -rf ./build ./*.egg-info; fi && "
            f"WITH_DEPENDENCY={with_dependency} python -m pip wheel --no-deps -w /io ."
        )
        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                build_command,
            ],
        )

        filenames = os.listdir(io_folder)
        orig_wheel = filenames[0]
        assert "manylinux" not in orig_wheel

        repair_command = (
            "LD_LIBRARY_PATH="
            "/auditwheel_src/tests/integration/testdependencies:$LD_LIBRARY_PATH "
            "auditwheel -v repair --plat {policy} -w /io /io/{orig_wheel}"
        )

        wheel_policy = WheelPolicies()
        policy_priority = wheel_policy.get_priority_by_name(policy)
        older_policies = [
            f"{p}_{PLATFORM}"
            for p in MANYLINUX_IMAGES
            if policy_priority < wheel_policy.get_priority_by_name(f"{p}_{PLATFORM}")
        ]
        for target_policy in older_policies:
            # we shall fail to repair the wheel when targeting an older policy than
            # the one matching the image
            with pytest.raises(CalledProcessError):
                docker_exec(
                    manylinux_ctr,
                    [
                        "bash",
                        "-c",
                        repair_command.format(
                            policy=target_policy, orig_wheel=orig_wheel
                        ),
                    ],
                )

        # check all works properly when targeting the policy matching the image
        docker_exec(
            manylinux_ctr,
            ["bash", "-c", repair_command.format(policy=policy, orig_wheel=orig_wheel)],
        )
        filenames = os.listdir(io_folder)
        assert len(filenames) == 2
        repaired_wheel = f"testdependencies-0.0.1-{PYTHON_ABI}-{tag}.whl"
        assert repaired_wheel in filenames
        assert_show_output(manylinux_ctr, repaired_wheel, policy, True)

        # check the original wheel with a dependency was not compliant
        # and check the one without a dependency was already compliant
        expected = f"linux_{PLATFORM}" if with_dependency == "1" else policy
        assert_show_output(manylinux_ctr, orig_wheel, expected, True)

        docker_exec(docker_python, "pip install /io/" + repaired_wheel)
        docker_exec(
            docker_python,
            [
                "python",
                "-c",
                "from sys import exit; from testdependencies import run; exit(run())",
            ],
        )

    @pytest.mark.parametrize(
        "target_policy",
        [f"{p}_{PLATFORM}" for p in list(MANYLINUX_IMAGES.keys())]
        + [f"{p}_{PLATFORM}" for aliases in POLICY_ALIASES.values() for p in aliases],
    )
    @pytest.mark.parametrize("only_plat", [True, False])
    def test_build_wheel_compat(
        self,
        target_policy,
        only_plat,
        any_manylinux_container,
        docker_python,
        io_folder,
    ):
        # test building wheels with compatibility with older spec
        # check aliases for older spec

        policy, tag, manylinux_ctr = any_manylinux_container

        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                "cd /auditwheel_src/tests/integration/testsimple "
                "&& python -m pip wheel --no-deps -w /io .",
            ],
        )

        filenames = os.listdir(io_folder)
        orig_wheel = filenames[0]
        assert "manylinux" not in orig_wheel

        if PLATFORM in {"x86_64", "i686"}:
            expect = f"manylinux_2_5_{PLATFORM}"
            expect_tag = f"manylinux_2_5_{PLATFORM}.manylinux1_{PLATFORM}"
        else:
            expect = f"manylinux_2_17_{PLATFORM}"
            expect_tag = f"manylinux_2_17_{PLATFORM}.manylinux2014_{PLATFORM}"

        target_tag = target_policy
        for pep600_policy, aliases in POLICY_ALIASES.items():
            policy_ = f"{pep600_policy}_{PLATFORM}"
            aliases_ = [f"{p}_{PLATFORM}" for p in aliases]
            if target_policy == policy_ or target_policy in aliases_:
                target_tag = f"{policy_}.{'.'.join(aliases_)}"

        only_plat_arg = "--only-plat" if only_plat else ""
        # we shall ba able to repair the wheel for all targets
        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                f"auditwheel -v repair --plat {target_policy} {only_plat_arg} -w /io"
                f" /io/{orig_wheel}",
            ],
        )
        filenames = os.listdir(io_folder)
        assert len(filenames) == 2
        if only_plat or target_tag == expect_tag:
            repaired_tag = target_tag
        else:
            repaired_tag = f"{expect_tag}.{target_tag}"
        repaired_wheel = f"testsimple-0.0.1-{PYTHON_ABI}-{repaired_tag}.whl"
        assert repaired_wheel in filenames

        assert_show_output(manylinux_ctr, repaired_wheel, expect, True)

        with zipfile.ZipFile(os.path.join(io_folder, repaired_wheel)) as z:
            for file in z.namelist():
                assert not file.startswith("testsimple.libs"), (
                    "should not have empty .libs folder"
                )

        docker_exec(docker_python, f"pip install /io/{repaired_wheel}")
        docker_exec(
            docker_python,
            [
                "python",
                "-c",
                "from sys import exit; from testsimple import run; exit(run())",
            ],
        )

    def test_zlib_blacklist(self, any_manylinux_container, io_folder):
        policy, tag, manylinux_ctr = any_manylinux_container
        if policy.startswith(("manylinux_2_17_", "manylinux_2_28_", "manylinux_2_34_")):
            pytest.skip(f"{policy} image has no blacklist symbols in libz.so.1")

        docker_exec(
            manylinux_ctr,
            [
                "bash",
                "-c",
                "cd /auditwheel_src/tests/integration/testzlib "
                "&& python -m pip wheel --no-deps -w /io .",
            ],
        )

        orig_wheel, *_ = os.listdir(io_folder)
        assert orig_wheel.startswith("testzlib-0.0.1")

        # Repair the wheel using the appropriate manylinux container
        repair_command = f"auditwheel repair --plat {policy} -w /io /io/{orig_wheel}"
        with pytest.raises(CalledProcessError):
            docker_exec(manylinux_ctr, repair_command)

        # Check auditwheel show warns about the black listed symbols
        output = docker_exec(manylinux_ctr, f"auditwheel -v show /io/{orig_wheel}")
        assert "black-listed symbol dependencies" in output.replace("\n", " ")


class TestMusllinux(Anylinux):
    @pytest.fixture(scope="session")
    def docker_python_img(self):
        """The alpine Python base image with up-to-date pip"""
        with tmp_docker_image(
            MUSLLINUX_PYTHON_IMAGE_ID, ["pip install -U pip"]
        ) as img_id:
            yield img_id

    @pytest.fixture(scope="session", params=MUSLLINUX_IMAGES.keys())
    def any_manylinux_img(self, request):
        """Each musllinux image, with auditwheel installed.

        Plus up-to-date pip, setuptools and pytest-cov
        """
        policy = request.param
        base = MUSLLINUX_IMAGES[policy]
        env = {"PATH": PATH[policy]}
        with tmp_docker_image(
            base,
            [
                'git config --global --add safe.directory "/auditwheel_src"',
                "pip install -U pip setuptools pytest-cov",
                "pip install -U -e /auditwheel_src",
            ],
            env,
        ) as img_id:
            yield policy, img_id
