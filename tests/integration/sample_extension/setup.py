from Cython.Build import cythonize
from setuptools import setup

setup(
    name="sample_extension",
    version="0.1.0",
    ext_modules=cythonize("src/sample_extension.pyx"),
)
