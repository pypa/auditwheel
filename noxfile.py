# /// script
# dependencies = ["nox>=2025.2.9"]
# ///

from __future__ import annotations

import os
import sys
from pathlib import Path

import nox

nox.needs_version = ">=2025.2.9"

PYTHON_ALL_VERSIONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]
RUNNING_CI = "TRAVIS" in os.environ or "GITHUB_ACTIONS" in os.environ

wheel = ""
sdist = ""


@nox.session(reuse_venv=True)
def lint(session: nox.Session) -> None:
    """
    Run linters on the codebase.
    """
    session.install("pre-commit")
    session.run("pre-commit", "run", "--all-files")


@nox.session(default=False)
def coverage(session: nox.Session) -> None:
    """
    Run coverage using unit tests.
    """
    pyproject = nox.project.load_toml("pyproject.toml")
    deps = nox.project.dependency_groups(pyproject, "coverage")
    session.install("-e", ".", *deps)
    session.run(
        "python",
        "-m",
        "pytest",
        "tests/unit",
        "--cov=auditwheel",
        "--cov-report=term-missing",
    )


def _docker_images(session: nox.Session) -> list[str]:
    tmp_dir = Path(session.create_tmp())
    script = tmp_dir / "list_images.py"
    images_file = tmp_dir / "images.lst"
    script.write_text(
        rf"""
import sys
from pathlib import Path
sys.path.append("./tests/integration")
from test_manylinux import MANYLINUX_IMAGES
images = "\n".join(MANYLINUX_IMAGES.values())
Path(r"{images_file}").write_text(images)
"""
    )
    session.run("python", str(script), silent=True)
    return images_file.read_text().splitlines()


@nox.session(python=PYTHON_ALL_VERSIONS, default=False)
def tests(session: nox.Session) -> None:
    """
    Run tests.
    """
    posargs = session.posargs
    dep_group = "coverage" if RUNNING_CI else "test"
    pyproject = nox.project.load_toml("pyproject.toml")
    deps = nox.project.dependency_groups(pyproject, dep_group)
    session.install("-U", "pip")
    session.install("-e", ".", *deps)
    # for tests/integration/test_bundled_wheels.py::test_analyze_wheel_abi_static_exe
    session.run(
        "pip",
        "download",
        "--only-binary",
        ":all:",
        "--no-deps",
        "--platform",
        "manylinux1_x86_64",
        "-d",
        "./tests/integration/",
        "patchelf==0.17.2.1",
    )
    if RUNNING_CI:
        posargs.extend(["--cov", "auditwheel", "--cov-branch"])
        # pull manylinux images that will be used.
        # this helps passing tests which would otherwise timeout.
        for image in _docker_images(session):
            session.run("docker", "pull", image, external=True)

    session.run("pytest", "-s", *posargs)
    if RUNNING_CI:
        session.run("auditwheel", "lddtree", sys.executable)
        session.run("coverage", "xml", "-ocoverage.xml")


@nox.session(python=["3.10"], default=False)
def build(session: nox.Session) -> None:
    session.install("build")
    tmp_dir = Path(session.create_tmp()) / "build-output"
    session.run("python", "-m", "build", "--outdir", str(tmp_dir))
    (wheel_path,) = tmp_dir.glob("*.whl")
    (sdist_path,) = tmp_dir.glob("*.tar.gz")
    Path("dist").mkdir(exist_ok=True)
    wheel_path.rename(f"dist/{wheel_path.name}")
    sdist_path.rename(f"dist/{sdist_path.name}")

    global sdist  # noqa: PLW0603
    sdist = f"dist/{sdist_path.name}"
    global wheel  # noqa: PLW0603
    wheel = f"dist/{wheel_path.name}"


def _test_dist(session: nox.Session, path: str) -> None:
    pyproject = nox.project.load_toml("pyproject.toml")
    deps = nox.project.dependency_groups(pyproject, "test")
    session.install(path, *deps)
    session.run("pytest", "tests/unit")


@nox.session(name="test-sdist", python=PYTHON_ALL_VERSIONS, requires=["build"])
def test_sdist(session: nox.Session) -> None:
    """
    Do not run explicitly.
    """
    _test_dist(session, sdist)


@nox.session(name="test-wheel", python=PYTHON_ALL_VERSIONS, requires=["build"])
def test_wheel(session: nox.Session) -> None:
    """
    Do not run explicitly.
    """
    _test_dist(session, wheel)


@nox.session(python=PYTHON_ALL_VERSIONS, reuse_venv=True, default=False)
def develop(session: nox.Session) -> None:
    session.run("python", "-m", "pip", "install", "--upgrade", "pip")
    pyproject = nox.project.load_toml("pyproject.toml")
    deps = nox.project.dependency_groups(pyproject, "dev")
    session.install("-e", ".", *deps)


if __name__ == "__main__":
    nox.main()
