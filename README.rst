deloc8
======

Cross-distribution Linux wheels.

``deloc8`` is a command line tool to facilitate the creation of Python
`wheel packages <http://pythonwheels.com/>`_ for Linux containing
pre-compiled binary extensions that can be widely distributed.

Using ``deloc8``, you can:

  * Copy external shared libraries that the extension depends on into the
    the wheel itself.

    Embedding the depended-upon shared libraries into the wheel helps ensure
    that the wheel will work on other users' machines, regardless of their
    Linux distribution they use, or the packages they've install with their
    distro package manager.

    For example, the ``numpy`` or ``scipy`` wheels may prefer to embed
    their own copy of BLAS or LAPACK, instead of simply crossing their
    fingers and hoping these shared libraries are provided by the system.

    ``deloc8`` is aware of a whitelist of system-provided libraries that
    are so ubiquitous (think of ``libc``, for example) that their
    existance on all Linux platforms can be essentially guarenteed. These
    whitelist(s) are part of the "platform policy" used by ``deloc8``.
    
  * Check and enforce proper symbol versions for system-provided libraries.
  
  
