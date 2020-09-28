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
            f'{package_name}.example_a',
            ['src/example_a.pyx'],
            include_dirs=['lib-src/a'],
            library_dirs=[package_name],
            libraries=['a'],
            extra_link_args=['-Wl,-rpath,$ORIGIN'],
        ),
        Extension(
            f'{package_name}.example_b',
            ['src/example_b.pyx'],
            include_dirs=['lib-src/b'],
            library_dirs=['lib-src/b'],
            libraries=['b'],
        ),
    ],
)
