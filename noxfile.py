from __future__ import annotations

import os
import sys
from pathlib import Path

import nox

nox.options.sessions = ["lint", "test-dist"]

PYTHON_ALL_VERSIONS = ["3.7", "3.8", "3.9", "3.10", "3.11"]
RUNNING_CI = "TRAVIS" in os.environ or "GITHUB_ACTIONS" in os.environ


@nox.session(python=["3.7"], reuse_venv=True)
def lint(session: nox.Session) -> None:
    """
    Run linters on the codebase.
    """
    session.install("pre-commit")
    session.run("pre-commit", "run", "--all-files")


@nox.session()
def coverage(session: nox.Session) -> None:
    """
    Run coverage using unit tests.
    """
    session.install(".[coverage]")
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


@nox.session(python=PYTHON_ALL_VERSIONS)
def tests(session: nox.Session) -> None:
    """
    Run tests.
    """
    posargs = session.posargs
    extras = "coverage" if RUNNING_CI else "test"
    session.install("-e", f".[{extras}]")
    if RUNNING_CI:
        session.install("codecov")
        posargs.extend(["--cov", "auditwheel", "--cov-branch"])
        # pull manylinux images that will be used.
        # this helps passing tests which would otherwise timeout.
        for image in _docker_images(session):
            session.run("docker", "pull", image, external=True)

    session.run("pytest", "-s", *posargs)
    if RUNNING_CI:
        session.run("auditwheel", "lddtree", sys.executable)
        try:
            session.run("codecov")
        except nox.command.CommandFailed:
            pass  # Ignore failures from codecov tool


def _build(session: nox.Session, dist: Path) -> None:
    session.install("build")
    tmp_dir = Path(session.create_tmp()) / "build-output"
    session.run("python", "-m", "build", "--outdir", str(tmp_dir))
    (wheel_path,) = tmp_dir.glob("*.whl")
    (sdist_path,) = tmp_dir.glob("*.tar.gz")
    dist.mkdir(exist_ok=True)
    wheel_path.rename(dist / wheel_path.name)
    sdist_path.rename(dist / sdist_path.name)


@nox.session(name="test-dist")
def test_dist(session: nox.Session) -> None:
    """
    Builds SDist & Wheels then run unit tests on those.
    """
    tmp_dir = Path(session.create_tmp())
    dist = tmp_dir / "dist"
    _build(session, dist)
    python_versions = session.posargs or PYTHON_ALL_VERSIONS
    for version in python_versions:
        session.notify(f"_test_sdist-{version}", [str(dist)])
        session.notify(f"_test_wheel-{version}", [str(dist)])


def _test_dist(session: nox.Session, path: str, pattern: str) -> None:
    (dist_path,) = Path(path).glob(pattern)
    session.install(f"{str(dist_path)}[test]")
    session.run("pytest", "tests/unit")


@nox.session(python=PYTHON_ALL_VERSIONS)
def _test_sdist(session: nox.Session) -> None:
    """
    Do not run explicitly.
    """
    _test_dist(session, session.posargs[0], "*.tar.gz")


@nox.session(python=PYTHON_ALL_VERSIONS)
def _test_wheel(session: nox.Session) -> None:
    """
    Do not run explicitly.
    """
    _test_dist(session, session.posargs[0], "*.whl")


@nox.session
def build(session: nox.Session) -> None:
    """
    Make an SDist and a wheel.
    """
    _build(session, Path("dist"))


@nox.session(python=PYTHON_ALL_VERSIONS, reuse_venv=True)
def develop(session: nox.Session) -> None:
    session.run("python", "-m", "pip", "install", "--upgrade", "pip", "setuptools")
    session.install("-e", ".[develop]")
