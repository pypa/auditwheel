from auditwheel.wheel_abi import analyze_wheel_abi


def test_analyze_wheel_abi_pypy_cffi():
    winfo = analyze_wheel_abi(
        'tests/python_snappy-0.5.2-pp260-pypy_41-linux_x86_64.whl')
    external_libs = winfo.external_refs['manylinux1_x86_64']['libs']
    assert len(external_libs) > 0
    assert set(external_libs) == {'libsnappy.so.1'}
