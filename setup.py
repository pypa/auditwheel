from setuptools import setup

extras = {
    "test": ["pytest>=3.4", "jsonschema", "pypatchelf", "pretend", "docker"],
    "coverage": ["pytest-cov"],
}
extras["develop"] = sum(extras.values(), [])
extras["coverage"] += extras["test"]

setup(extras_require=extras)
