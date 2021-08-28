import os
import sys

from pathlib import Path

import nox


RUNNING_CI = "TRAVIS" in os.environ or "GITHUB_ACTIONS" in os.environ


@nox.session(python=["3.6"], reuse_venv=True)
def lint(session: nox.Session) -> None:
    """
    Run linters on the codebase.
    """
    session.install("pre-commit")
    session.run("pre-commit", "run", "--all-files")


@nox.session()
def coverage(session: nox.Session) -> str:
    """
    Run coverage using unit tests.
    """
    session.install("-r", "test-requirements.txt", "pytest-cov")
    session.run(
        "python",
        "-m",
        "pytest",
        "tests/unit",
        "--cov=auditwheel",
        "--cov-report=term-missing"
    )


def _docker_images(session):
    tmp_dir = Path(session.create_tmp())
    script = tmp_dir / "list_images.py"
    images_file = tmp_dir / "images.lst"
    script.write_text(
        fr"""
from pathlib import Path
from tests.integration.test_manylinux import MANYLINUX_IMAGES
images = "\n".join(MANYLINUX_IMAGES.values())
Path(r"{images_file}").write_text(images)
"""
    )
    session.run("python", str(script), silent=True)
    return images_file.read_text().splitlines()


@nox.session(python=["3.6", "3.7", "3.8", "3.9"])
def tests(session: nox.Session) -> str:
    """
    Run tests.
    """
    posargs = session.posargs
    session.install("-r", "test-requirements.txt", "-e", ".")
    if RUNNING_CI:
        session.install("pytest-cov", "codecov")
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
