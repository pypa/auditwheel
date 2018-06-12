from setuptools import setup
import subprocess

cmd = 'gcc testpackage/testprogram.c -lgsl -o testpackage/testprogram'
subprocess.check_call(cmd.split())

setup(
    name='testpackage',
    packages=['testpackage'],
    package_data={'testpackage': ['testprogram']}
)
