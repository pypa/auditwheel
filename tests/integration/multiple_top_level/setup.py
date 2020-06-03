from setuptools import setup, Extension, find_packages


setup(
    name='multiple_top_level',
    version='1.0',
    description='Auditwheel multiple top-level extensions example',
    packages=find_packages(where='src'),
    ext_modules=[
        Extension(
            'example_a',
            ['src/example_a.pyx'],
            include_dirs=['lib-src/a'],
            library_dirs=['lib-src/a', 'lib-src/b'],
            libraries=['a'],
        ),
        Extension(
            'example_b',
            ['src/example_b.pyx'],
            include_dirs=['lib-src/a'],
            library_dirs=['lib-src/a', 'lib-src/b'],
            libraries=['a'],
        ),
    ],
)
