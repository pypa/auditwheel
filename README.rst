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
  that the wheel will work on other users' machines, regardless of what
  distro they use, or what libraries they've install with their distro
  package manager.

  But ``deloc8`` is aware of a whitelist of system libraries that are so
  ubiquitous (think of ``libc``, for example) that their existance on
  all Linux platforms can be essentially guarenteed. So it doesn't need
  to copy everything into the wheel.
  
* Check and enforce proper symbol versions for system-provided libraries.
  
  
