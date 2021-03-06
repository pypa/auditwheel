import platform
from pathlib import Path
import pytest
from auditwheel.wheel_abi import analyze_wheel_abi


HERE = Path(__file__).parent.resolve()


@pytest.mark.skipif(platform.machine() != 'x86_64', reason='only supported on x86_64')
@pytest.mark.parametrize('file, external_libs', [
    ('cffi-1.5.0-cp27-none-linux_x86_64.whl', {'libffi.so.5'}),
    ('python_snappy-0.5.2-pp260-pypy_41-linux_x86_64.whl', {'libsnappy.so.1'}),
])
def test_analyze_wheel_abi(file, external_libs):
    winfo = analyze_wheel_abi(str(HERE / file))
    assert set(winfo.external_refs['manylinux_2_5_x86_64']['libs']) == external_libs


@pytest.mark.skipif(platform.machine() != 'x86_64', reason='only supported on x86_64')
def test_analyze_wheel_abi_pyfpe():
    winfo = analyze_wheel_abi(str(HERE / 'fpewheel-0.0.0-cp35-cp35m-linux_x86_64.whl'))
    assert winfo.sym_tag == 'manylinux_2_5_x86_64'  # for external symbols, it could get manylinux1
    assert winfo.pyfpe_tag == 'linux_x86_64'        # but for having the pyfpe reference, it gets just linux
