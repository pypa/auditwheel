from unittest.mock import Mock
from pathlib import Path

from auditwheel.main_addtag import execute

HERE = Path(__file__).parent.resolve()

def test_smoke(tmpdir):
    """Simple test to exercise the 'addtag' code path"""
    args = Mock(WHEEL_FILE=str(HERE / "cffi-1.5.0-cp27-none-linux_x86_64.whl"),
                WHEEL_DIR=str(tmpdir / "wheelhouse/"))
    execute(args, None)
