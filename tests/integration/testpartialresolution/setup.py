from __future__ import annotations

import subprocess
from pathlib import Path

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class BuildExt(build_ext):
    def run(self) -> None:
        outputs = self.get_outputs()
        assert len(outputs) == 1
        liba_path = Path(outputs[0]).parent / "liba.so"
        libb_path = Path(outputs[0]).parent / "libb.so"

        cmd = f"gcc -fPIC -shared -o {libb_path} b/b.c"
        subprocess.check_call(cmd.split())
        libb_parent_path = libb_path.parent.resolve(strict=True)
        cmd = f"gcc -fPIC -shared -o {liba_path} -Ib a/a.c -L{libb_parent_path} -lb"
        subprocess.check_call(cmd.split())
        liba_path = liba_path.resolve(strict=True)
        liba_link_path = Path("a/liba.so")
        if liba_link_path.exists():
            liba_link_path.unlink()
        liba_link_path.symlink_to(liba_path)

        super().run()


setup(
    name="testpartialresolution",
    version="0.0.1",
    packages=["testpartialresolution"],
    package_dir={"": "src"},
    cmdclass={"build_ext": BuildExt},
    ext_modules=[
        Extension(
            "testpartialresolution/testpartialresolution",
            sources=["src/testpartialresolution/testpartialresolution.c"],
            extra_link_args=["-Wl,--disable-new-dtags", "-Wl,-rpath=$ORIGIN"],
            include_dirs=["a"],
            libraries=["a"],
            library_dirs=["a"],
        ),
    ],
)
