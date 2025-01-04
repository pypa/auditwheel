from __future__ import annotations

from setuptools import setup

extras = {
    "test": ["pytest>=3.4", "jsonschema", "pypatchelf", "pretend", "docker"],
    "coverage": ["pytest-cov"],
}
extras["coverage"] += extras["test"]
extras["develop"] = list({dep for deps in extras.values() for dep in deps})

setup(extras_require=extras)
