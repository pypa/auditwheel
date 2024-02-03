from __future__ import annotations

import subprocess

from setuptools import setup

subprocess.check_call(
    (
        "gcc",
        "testpackage/testprogram.c",
        "-lgsl",
        "-lgslcblas",
        "-o",
        "testpackage/testprogram",
    )
)
subprocess.check_call(
    ("gcc", "testpackage/testprogram_nodeps.c", "-o", "testpackage/testprogram_nodeps")
)

setup(
    name="testpackage",
    version="0.0.1",
    packages=["testpackage"],
    package_data={"testpackage": ["testprogram", "testprogram_nodeps"]},
    # This places these files at a path like
    # "testpackage-0.0.1.data/scripts/testprogram", which is needed to test
    # rewriting ELF binaries installed into the scripts directory.
    #
    # Note that using scripts=[] doesn't work here since setuptools expects the
    # scripts to be text and tries to decode them using UTF-8.
    data_files=[
        ("../scripts", ["testpackage/testprogram", "testpackage/testprogram_nodeps"])
    ],
)
