import subprocess

from setuptools import setup

cmd = "gcc testpackage/testprogram.c -lgsl -lgslcblas -o testpackage/testprogram"
subprocess.check_call(cmd.split())

setup(
    name="testpackage",
    version="0.0.1",
    packages=["testpackage"],
    package_data={"testpackage": ["testprogram"]},
)
