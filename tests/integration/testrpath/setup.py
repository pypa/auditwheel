from __future__ import annotations

import os
import subprocess

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext

USE_DTAGS = os.getenv("DTAG") != "none"


class BuildExt(build_ext):
    def run(self) -> None:
        use_runpath = os.getenv("DTAG") == "runpath"
        dtags_kind_flag = "--enable-new-dtags" if use_runpath else "--disable-new-dtags"
        dtags = f"-Wl,{dtags_kind_flag} -Wl,-rpath=$ORIGIN/../b" if USE_DTAGS else ""

        cmd = f"gcc -fPIC -shared -o b/libb.so {dtags} b/b.c"
        subprocess.check_call(cmd.split())

        dtags = f"-Wl,{dtags_kind_flag} -Wl,-rpath=$ORIGIN/../b" if USE_DTAGS else ""
        cmd = f"gcc -fPIC -shared -o a/liba.so {dtags} -Ib a/a.c -Lb -lb"
        subprocess.check_call(cmd.split())
        super().run()


setup(
    name="testrpath",
    version="0.0.1",
    packages=["testrpath"],
    package_dir={"": "src"},
    cmdclass={"build_ext": BuildExt},
    ext_modules=[
        Extension(
            "testrpath/testrpath",
            sources=["src/testrpath/testrpath.c"],
            include_dirs=["a"],
            libraries=["a"],
            library_dirs=["a"] if USE_DTAGS else ["a", "b"],
        ),
    ],
)
