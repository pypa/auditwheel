from setuptools import Extension, find_packages, setup


setup(
    name="example_runpath",
    version="1.0",
    description="Auditwheel extension using libraries with RUNPATH being set",
    packages=find_packages(where="src"),
    package_dir={'': 'src'},
    ext_modules=[
        Extension(
            "example_runpath.example",
            ["src/example_runpath/example.pyx"],
            include_dirs=["lib-src/a"],
            library_dirs=["lib-src/a"],
            libraries=["a"],
        )
    ],
)
