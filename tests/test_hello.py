import os
import os.path as op
import shutil
from test_manylinux import \
    docker_container, \
    docker_exec, \
    WHEEL_CACHE_FOLDER

HELLO_WHEEL = 'hello-0.1.0-cp35-cp35m-linux_x86_64.whl'


def build_hello_wheel(docker_container):
    policy, manylinux_id, python_id, io_folder = docker_container

    if op.exists(op.join(WHEEL_CACHE_FOLDER, HELLO_WHEEL)):
        # If hello has already been built and put in cache, let's reuse this.
        shutil.copy2(op.join(WHEEL_CACHE_FOLDER, HELLO_WHEEL),
                     op.join(io_folder, HELLO_WHEEL))
    else:
        docker_exec(manylinux_id,
                    'pip wheel -w /io /auditwheel_src/tests/pr134/hello_module/')
        shutil.copy2(op.join(io_folder, HELLO_WHEEL),
                     op.join(WHEEL_CACHE_FOLDER, HELLO_WHEEL))
    filenames = os.listdir(io_folder)
    assert filenames == [HELLO_WHEEL]
    orig_wheel = filenames[0]
    assert 'manylinux' not in orig_wheel
    return orig_wheel


def test_detect_external_dependency_in_wheel(docker_container):
    # tests https://github.com/pypa/auditwheel/issues/136
    policy, manylinux_id, python_id, io_folder = docker_container
    orig_wheel = build_hello_wheel(docker_container)

    output = docker_exec(manylinux_id, 'auditwheel show /io/' + orig_wheel)
    assert (
        'In order to achieve the tag platform tag "manylinux1_x86_64" the'
        'following shared library dependencies will need to be eliminated:'
        'libz.so.1'
        'lib_zlibexample.cpython-35m-x86_64-linux-gnu.so'
    ) in output.replace('\n', '')


def test_repair_hello_wheel(docker_container):
    policy, manylinux_id, python_id, io_folder = docker_container
    orig_wheel = build_hello_wheel(docker_container)
    # attempting repair of the hello wheel

    # Repair the wheel using the manylinux container
    repair_command = (
        'auditwheel repair --plat {policy}_x86_64 -w /io /io/{orig_wheel}'
    ).format(policy=policy, orig_wheel=orig_wheel)
    docker_exec(manylinux_id, repair_command)
    filenames = os.listdir(io_folder)

    # Regardless of build environment, wheel only needs manylinux1 symbols
    repaired_wheels = [fn for fn in filenames if 'manylinux1' in fn]
    assert repaired_wheels == ['hello-0.1.0-cp35-cp35m-manylinux1_x86_64.whl']
    repaired_wheel = repaired_wheels[0]

    output = docker_exec(manylinux_id, 'auditwheel show /io/' + repaired_wheel)
    assert (
        'hello-0.1.0-cp35-cp35m-manylinux1_x86_64.whl is consistent with the'
        'following platform tag: "manylinux1_x86_64"'
    ) in output.replace('\n', '')

    # Test whether wheel is functioning.

    # TODO: Remove once pip supports manylinux2010
    docker_exec(
        python_id,
        "pip install git+https://github.com/wtolson/pip.git@manylinux2010",
    )

    test_commands = [
        'pip install -U /io/' + repaired_wheel,
        '''python -c "from hello import z_compress, z_uncompress; assert z_uncompress(z_compress('test')) == 'test'"''',
    ]
    for cmd in test_commands:
        docker_exec(python_id, cmd)


# from auditwheel.wheel_abi import analyze_wheel_abi
# def test_analyze_wheel_abi_hello():
#     winfo = analyze_wheel_abi(
#         'tests/python_snappy-0.5.2-pp260-pypy_41-linux_x86_64.whl')
#     external_libs = winfo.external_refs['manylinux1_x86_64']['libs']
#     assert len(external_libs) > 0
#     assert set(external_libs) == {'libsnappy.so.1'}
