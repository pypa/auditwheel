import sysconfig
from setuptools import setup, Extension
import subprocess
from os import path
from os import getenv

# Build the string reverser library (an example library)
cmd = "gcc -Wall -shared -fPIC nonpy_dependency.cpp -o libnonpy_dependency.so"
subprocess.check_call(cmd.split())

# Build the dependency that calls the string reverser
python_include_dir = sysconfig.get_paths()["include"]
current_dir = path.abspath(path.dirname(__file__))
cmd = f"gcc -Wall -shared -fPIC -I{python_include_dir} -L{current_dir} dependency.cpp -o libdependency.so -Wl,-rpath={current_dir} -lnonpy_dependency"
subprocess.check_call(cmd.split())

libraries = ["dependency"]
library_dirs = [current_dir]

setup(
    name="test_nonpy_dependencies",
    version="0.0.1",
    ext_modules=[
        Extension(
            "test_nonpy_dependencies",
            sources=["testdependencies.cpp"],
            libraries=libraries,
            library_dirs=library_dirs,
            runtime_library_dirs=["$ORIGIN"],
        )
    ],
)
