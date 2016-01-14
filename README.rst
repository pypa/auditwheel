auditwheel
==========

Auditing and relabeling cross-distribution Linux wheels.

Overview
--------

``auditwheel`` is a command line tool to facilitate the creation of Python
`wheel packages <http://pythonwheels.com/>`_ for Linux containing
pre-compiled binary extensions that can be expected to be compatible
with a wide variety of Linux distributions because they use only a small
standard subset of the kernel+core userspace ABI.

``auditwheel show``: shows external shared libraries that the wheel depends on
(beyond the libraries included in the ``manylinux_1`` policy), and
checks the extension modules for the use of versioned symbols that exceed
the ``manylinux_1`` ABI.


Installation
-------------

``auditwheel`` can be installed using pip: ::

  pip install git+git://github.com/manylinux/auditwheel

It requires Python 3.3+, and runs on Linux. It requires that the shell command
``unzip`` be available in the ``PATH``. Only systems that use
`ELF <https://en.wikipedia.org/wiki/Executable_and_Linkable_Format>`_-based
linkage are supported (this should be essentially every Linux).


Examples
--------

Inspecting a wheel: ::

  $ manylinux show numpy-1.10.4-cp35-cp35m-linux_x86_64.whl

  numpy-1.10.4-cp35-cp35m-linux_x86_64.whl is consistent with the
  following platform tag: "linux_x86_64".

  The wheel references the following external versioned symbols in
  system-provided shared libraries: GLIBC_2.3, GLIBC_2.2.5.

  The following external shared libraries are required by the wheel:
  {
      "libgfortran.so.1": "/usr/lib64/libgfortran.so.1.0.0",
      "libm.so.6": "/lib64/libm-2.5.so",
      "libc.so.6": "/lib64/libc-2.5.so",
      "libopenblas.so.0": "/usr/local/lib/libopenblas_nehalemp-r0.2.14.so",
      "libpthread.so.0": "/lib64/libpthread-2.5.so"
  }

  In order to achieve the tag platform tag "manylinux_1" the following
  shared library dependencies would need to be eliminated:

  libgfortran.so.1, libopenblas.so.0

Limitations
-----------

1. ``auditwheel`` uses the `DT_NEEDED <https://en.wikipedia.org/wiki/Direct_binding>`_
   information from the Python extension modules to determine which system system
   libraries they depend on. Code that that dynamically loads libraries at
   at runtime using ``ctypes`` / ``cffi`` (from Python) or ``dlopen`` (from C/C++)
   doesn't contain this information in a way that can be statically determined, so
   dependencies that are loaded via those mechanisms will be missed.
2. There's nothing we can do about "fixing" binaries if they were compiled and linked
   against a too-recent version of ``libc`` ot ``libstdc++``. These libraries
   (and some others) use symbol versioning for backward compatibility. In general, this
   means that code that was compiled against an old version of ``glibc`` will run
   fine on systems with a newer version of ``glibc``, but code what was compiled
   on a new system won't / might not run on older system.

   So, to compile widely-compatible binaries, you're best off doing the build on an
   old Linux distribution. The ``linux_pybe1_core`` platform tag is consistent with
   symbol versions from CentOS 5. Fortunately with Docker, this is hard anymore.


Policies
--------

The exact content of the policy is open for discussion. For example, here's a
first draft.

::

    {"name": "manylinux_1",
     "symbol_versions": {
         "GLIBC": "2.5",
         "CXXABI": "3.4.8",
         "GLIBCXX": "3.4.9",
         "GCC": "4.2.0"},
     "lib_whitelist": [
         "libpanelw.so.5", "libncursesw.so.5",
         "libgcc_s.so.1",
         "libstdc++.so.6",
         "libm.so.6", "libdl.so.2", "librt.so.1", "libcrypt.so.1",
         "libc.so.6", "libnsl.so.1", "libutil.so.1", "libpthread.so.0",
         "libX11.so.6", "libXext.so.6", "libXrender.so.1", "libICE.so.6",
         "libSM.so.6", "libGL.so.1", "libgobject-2.0.so.0",
         "libgthread-2.0.so.0", "libglib-2.0.so.0"
     ]}


The tool is desined to support multiple policies with different whitelists, but
currently there's just one (well, two if you count the generic "linux" policy,
which enforces zero constraints).
