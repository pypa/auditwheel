import setuptools.command.build_ext
from setuptools import setup, find_packages, Distribution
from setuptools.extension import Extension, Library
import os

# despite its name, setuptools.command.build_ext.link_shared_object won't
# link a shared object on Linux, but a static library and patches distutils
# for this ... We're patching this back now.


def always_link_shared_object(
    self,
    objects,
    output_libname,
    output_dir=None,
    libraries=None,
    library_dirs=None,
    runtime_library_dirs=None,
    export_symbols=None,
    debug=0,
    extra_preargs=None,
    extra_postargs=None,
    build_temp=None,
    target_lang=None,
):
    self.link(
        self.SHARED_LIBRARY,
        objects,
        output_libname,
        output_dir,
        libraries,
        library_dirs,
        runtime_library_dirs,
        export_symbols,
        debug,
        extra_preargs,
        extra_postargs,
        build_temp,
        target_lang,
    )


setuptools.command.build_ext.libtype = "shared"
setuptools.command.build_ext.link_shared_object = always_link_shared_object

libtype = setuptools.command.build_ext.libtype
build_ext_cmd = Distribution().get_command_obj("build_ext")
build_ext_cmd.initialize_options()
build_ext_cmd.setup_shlib_compiler()


def libname(name):
    """ gets 'name' and returns something like libname.cpython-37m-darwin.so"""
    filename = build_ext_cmd.get_ext_filename(name)
    fn, ext = os.path.splitext(filename)
    return build_ext_cmd.shlib_compiler.library_filename(fn, libtype)


pkg_name = "nonpy_rpath"
crypt_name = "_cryptexample"
crypt_soname = libname(crypt_name)

build_cmd = Distribution().get_command_obj("build")
build_cmd.finalize_options()
build_platlib = build_cmd.build_platlib


def link_args(soname=None):
    args = []
    if soname:
        args += ["-Wl,-soname," + soname]
    loader_path = "$ORIGIN"
    args += ["-Wl,-rpath," + loader_path]
    return args


nonpy_rpath_module = Extension(
    pkg_name + "._nonpy_rpath",
    language="c++",
    sources=["nonpy_rpath.cpp"],
    extra_link_args=link_args(),
    extra_objects=[build_platlib + "/nonpy_rpath/" + crypt_soname],
)
crypt_example = Library(
    pkg_name + "." + crypt_name,
    language="c++",
    extra_compile_args=["-lcrypt"],
    extra_link_args=link_args(crypt_soname) + ["-lcrypt"],
    sources=["extensions/testcrypt.cpp"],
)

setup(
    name="nonpy_rpath",
    version="0.1.0",
    packages=find_packages(),
    description="Test package for nonpy_rpath",
    ext_modules=[crypt_example, nonpy_rpath_module],
)
