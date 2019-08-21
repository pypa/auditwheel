# Python 3 extension with non-Python library dependency

This example was inspired from https://gist.github.com/physacco/2e1b52415f3a964ad2a542a99bebed8f

This test extension builds two libraries: `_nonpy_rpath.*.so` and `lib_cryptexample.*.so`, where the `*` is a string composed of Python ABI versions and platform tags.

The extension `lib_cryptexample.*.so` should be repaired by auditwheel because it is a needed library, even though it is not a Python extension.

[Issue #136](https://github.com/pypa/auditwheel/issues/136) documents the underlying problem that this test case is designed to solve.
