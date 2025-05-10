from __future__ import annotations

import os
import subprocess

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class BuildExt(build_ext):
    def run(self) -> None:
        cmd = "gcc -fPIC -shared -o c/libc.so c/c.c"
        subprocess.check_call(cmd.split())
        cmd = "gcc -fPIC -shared -o b/libb.so b/b.c -Ic -Lc -lc"
        subprocess.check_call(cmd.split())
        cmd = (
            "gcc -fPIC -shared -o a/liba.so a/a.c "
            "-Wl,{dtags_flag} -Wl,-rpath=$ORIGIN/../b -Wl,-rpath=$ORIGIN/../c "
            "-Ib -Lb -lb -Ic -Lc -lc"
        ).format(
            dtags_flag=(
                "--enable-new-dtags"
                if os.getenv("DTAG") == "runpath"
                else "--disable-new-dtags"
            )
        )
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
            library_dirs=["a"],
        )
    ],
)
