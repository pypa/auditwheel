from __future__ import annotations

import subprocess
from os import getenv, path

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext

define_macros = [("_GNU_SOURCE", None)]
libraries = []
library_dirs = []
extra_compile_args = []

if getenv("WITH_DEPENDENCY", "0") == "1":
    libraries.append("dependency")
    library_dirs.append(path.abspath(path.dirname(__file__)))
    define_macros.append(("WITH_DEPENDENCY", "1"))

if getenv("WITH_ARCH", "") != "":
    extra_compile_args.extend((f"-march={getenv('WITH_ARCH')}", "-mneeded"))

libraries.extend(["m", "c"])


class BuildExt(build_ext):
    def run(self) -> None:
        cflags = ("-shared", "-fPIC", "-D_GNU_SOURCE", *extra_compile_args)
        cmd = f"gcc {' '.join(cflags)} dependency.c -o libdependency.so -lm -lc"
        subprocess.check_call(cmd.split())
        super().run()


setup(
    name="testdependencies",
    version="0.0.1",
    cmdclass={"build_ext": BuildExt},
    ext_modules=[
        Extension(
            "testdependencies",
            sources=["testdependencies.c"],
            extra_compile_args=extra_compile_args,
            define_macros=define_macros,
            libraries=libraries,
            library_dirs=library_dirs,
        ),
    ],
)
