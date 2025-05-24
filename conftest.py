import os

import pytest

@pytest.fixture(autouse=True, scope="session")
def clean_env():
    variables = ("AUDITWHEEL_PLAT", "AUDITWHEEL_ZIP_COMPRESSION_LEVEL")
    for var in variables:
        os.environ.pop(var, None)
