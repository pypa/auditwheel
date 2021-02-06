#!/usr/bin/env python3
# encoding: utf-8

import platform
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


pkg_name = "hello"
zlib_name = "_zlibexample"
zlib_soname = libname(zlib_name)

build_cmd = Distribution().get_command_obj("build")
build_cmd.finalize_options()
build_platlib = build_cmd.build_platlib


def link_args(soname=None):
    args = []
    if platform.system() == "Linux":
        if soname:
            args += ["-Wl,-soname," + soname]
        loader_path = "$ORIGIN"
        args += ["-Wl,-rpath," + loader_path]
    elif platform.system() == "Darwin":
        if soname:
            args += ["-Wl,-dylib", "-Wl,-install_name,@rpath/%s" % soname]
        args += ["-Wl,-rpath,@loader_path/"]
    return args


hello_module = Extension(
    pkg_name + "._hello",
    language="c++",
    sources=["hello.cpp"],
    extra_link_args=link_args(),
    extra_objects=[build_platlib + "/hello/" + zlib_soname],
)
zlib_example = Library(
    pkg_name + "." + zlib_name,
    language="c++",
    extra_compile_args=["-lz"],
    extra_link_args=link_args(zlib_soname) + ["-lz"],
    sources=["extensions/testzlib.cpp"],
)

setup(
    name="hello",
    version="0.1.0",
    packages=find_packages(),
    description="Hello world module written in C",
    ext_modules=[zlib_example, hello_module],
)
