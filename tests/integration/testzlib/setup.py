from setuptools import Extension, setup

define_macros = [("_GNU_SOURCE", None)]
libraries = ["z", "c"]

setup(
    name="testzlib",
    version="0.0.1",
    ext_modules=[
        Extension(
            "testzlib",
            sources=["testzlib.c"],
            define_macros=define_macros,
            libraries=libraries,
        )
    ],
)
