auditwheel
==========

.. image:: https://travis-ci.org/pypa/auditwheel.svg?branch=master
    :target: https://travis-ci.org/pypa/auditwheel
.. image:: https://badge.fury.io/py/auditwheel.svg
    :target: https://pypi.org/project/auditwheel

Auditing and relabeling of `PEP 513 manylinux1
<https://www.python.org/dev/peps/pep-0513/>`_ and `PEP 571 manylinux2010
<https://www.python.org/dev/peps/pep-0571/>`_ Linux wheels.

Overview
--------

``auditwheel`` is a command line tool to facilitate the creation of Python
`wheel packages <http://pythonwheels.com/>`_ for Linux containing pre-compiled
binary extensions are compatible with a wide variety of Linux distributions,
consistent with the `PEP 513 manylinux1
<https://www.python.org/dev/peps/pep-0513/>`_ and `PEP 571 manylinux2010
<https://www.python.org/dev/peps/pep-0571/>`_ platform tags.

``auditwheel show``: shows external shared libraries that the wheel depends on
(beyond the libraries included in the ``manylinux`` policies), and
checks the extension modules for the use of versioned symbols that exceed
the ``manylinux`` ABI.

``auditwheel repair``: copies these external shared libraries into the wheel itself, and automatically modifies the appropriate ``RPATH`` entries such that these libraries will be picked up at runtime. This accomplishes a similar result as if the libraries had been statically linked without requiring changes to the build system. Packagers are advised that bundling, like static linking, may implicate copyright concerns.


Installation
-------------

``auditwheel`` can be installed using pip: ::

  pip3 install auditwheel

It requires Python 3.5+, and runs on Linux. It requires that the shell command
``unzip`` be available in the ``PATH``. Only systems that use `ELF
<https://en.wikipedia.org/wiki/Executable_and_Linkable_Format>`_-based linkage
are supported (this should be essentially every Linux).

In general, building ``manylinux1`` wheels requires running on a CentOS5
machine, and building ``manylinux2010`` wheels requires running on a CentOS6
machine, so we recommend using the pre-built manylinux `Docker images
<https://quay.io/repository/pypa/manylinux1_x86_64>`_, e.g. ::

  $ docker run -i -t -v `pwd`:/io quay.io/pypa/manylinux1_x86_64 /bin/bash


Examples
--------

Inspecting a wheel: ::

    $ auditwheel show cffi-1.5.0-cp35-cp35m-linux_x86_64.whl

    cffi-1.5.0-cp35-cp35m-linux_x86_64.whl is consistent with the
    following platform tag: "linux_x86_64".

    The wheel references the following external versioned symbols in
    system-provided shared libraries: GLIBC_2.3.

    The following external shared libraries are required by the wheel:
    {
        "libc.so.6": "/lib64/libc-2.5.so",
        "libffi.so.5": "/usr/lib64/libffi.so.5.0.6",
        "libpthread.so.0": "/lib64/libpthread-2.5.so"
    }

    In order to achieve the tag platform tag "manylinux1_x86_64" the
    following shared library dependencies will need to be eliminated:

    libffi.so.5

Repairing a wheel. ::

    $ auditwheel repair cffi-1.5.2-cp35-cp35m-linux_x86_64.whl
    Repairing cffi-1.5.2-cp35-cp35m-linux_x86_64.whl
    Grafting: /usr/lib64/libffi.so.5.0.6
    Setting RPATH: _cffi_backend.cpython-35m-x86_64-linux-gnu.so to "$ORIGIN/.libs_cffi_backend"
    Previous filename tags: linux_x86_64
    New filename tags: manylinux1_x86_64
    Previous WHEEL info tags: cp35-cp35m-linux_x86_64
    New WHEEL info tags: cp35-cp35m-manylinux1_x86_64
    
    Fixed-up wheel written to /wheelhouse/cffi-1.5.2-cp35-cp35m-manylinux1_x86_64.whl


Limitations
-----------

1. ``auditwheel`` uses the `DT_NEEDED <https://en.wikipedia.org/wiki/Direct_binding>`_
   information (like ``ldd``) from the Python extension modules to determine
   which system system libraries they depend on. Code that that dynamically
   loads libraries at at runtime using ``ctypes`` / ``cffi`` (from Python) or
   ``dlopen`` (from C/C++) doesn't contain this information in a way that can
   be statically determined, so dependencies that are loaded via those
   mechanisms will be missed.
2. There's nothing we can do about "fixing" binaries if they were compiled and
   linked against a too-recent version of ``libc`` or ``libstdc++``. These
   libraries (and some others) use symbol versioning for backward
   compatibility. In general, this means that code that was compiled against an
   old version of ``glibc`` will run fine on systems with a newer version of
   ``glibc``, but code what was compiled on a new system won't / might not run
   on older system.

   So, to compile widely-compatible binaries, you're best off doing the build
   on an old Linux distribution, such as the manylinux Docker image.


Code of Conduct
---------------

Everyone interacting in the auditwheel project's codebases, issue trackers,
chat rooms, and mailing lists is expected to follow the
`PyPA Code of Conduct`_.

.. _PyPA Code of Conduct: https://www.pypa.io/en/latest/code-of-conduct/
