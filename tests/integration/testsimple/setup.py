from setuptools import Extension, setup

setup(
    name="testsimple",
    version="0.0.1",
    ext_modules=[Extension("testsimple", sources=["testsimple.c"])],
)
