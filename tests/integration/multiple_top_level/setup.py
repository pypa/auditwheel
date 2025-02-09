from __future__ import annotations

from setuptools import Extension, find_packages, setup

setup(
    name="multiple_top_level",
    version="0.0.1",
    description="Auditwheel multiple top-level extensions example",
    packages=find_packages(where="src"),
    ext_modules=[
        Extension(
            "example_a",
            ["src/example_a.pyx"],
            include_dirs=["lib-src/a"],
            library_dirs=["lib-src/a", "lib-src/b"],
            libraries=["a"],
        ),
        Extension(
            "example_b",
            ["src/example_b.pyx"],
            include_dirs=["lib-src/a"],
            library_dirs=["lib-src/a", "lib-src/b"],
            libraries=["a"],
        ),
    ],
)
