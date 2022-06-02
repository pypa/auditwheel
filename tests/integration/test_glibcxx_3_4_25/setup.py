from setuptools import Extension, setup

setup(
    name="testentropy",
    version="0.0.1",
    ext_modules=[
        Extension(
            "testentropy",
            language="c++",
            sources=["testentropy.cpp"],
            extra_compile_args=["-std=c++11"],
        ),
    ],
)
