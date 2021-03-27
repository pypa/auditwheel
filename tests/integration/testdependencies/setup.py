from setuptools import setup, Extension
import subprocess
from os import path
from os import getenv

cmd = 'gcc -shared -fPIC -D_GNU_SOURCE dependency.c -o libdependency.so -lm -lc'
subprocess.check_call(cmd.split())

define_macros = [('_GNU_SOURCE', None)]
libraries = []
library_dirs = []

if getenv('WITH_DEPENDENCY', '0') == '1':
    libraries.append('dependency')
    library_dirs.append(path.abspath(path.dirname(__file__)))
    define_macros.append(('WITH_DEPENDENCY', '1'))

libraries.extend(['m', 'c'])

setup(
    name='testdependencies',
    version='0.0.1',
    ext_modules=[Extension('testdependencies', sources=['testdependencies.c'], define_macros=define_macros, libraries=libraries, library_dirs=library_dirs)],
)
