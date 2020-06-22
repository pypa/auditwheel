from setuptools import setup, Extension, find_packages

package_name = 'internal_rpath'
setup(
    name=package_name,
    version='1.0',
    description='Auditwheel multiple top-level extensions example',
    package_data={package_name: ['liba.so']},
    packages=find_packages(),
    ext_modules=[
        Extension(
            '{}.example_a'.format(package_name),
            ['src/example_a.pyx'],
            include_dirs=['lib-src/a'],
            library_dirs=[package_name],
            libraries=['a'],
            extra_link_args=['-Wl,-rpath,$ORIGIN'],
        ),
        Extension(
            '{}.example_b'.format(package_name),
            ['src/example_b.pyx'],
            include_dirs=['lib-src/b'],
            library_dirs=['lib-src/b'],
            libraries=['b'],
        ),
    ],
)
