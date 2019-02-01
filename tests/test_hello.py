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


def repair_hello_wheel(orig_wheel, docker_container):
    policy, manylinux_id, python_id, io_folder = docker_container
    # Repair the wheel using the manylinux container
    repair_command = (
        'auditwheel repair --plat {policy}_x86_64 -w /io /io/{orig_wheel}'
    ).format(policy=policy, orig_wheel=orig_wheel)
    docker_exec(manylinux_id, repair_command)
    filenames = os.listdir(io_folder)

    # Regardless of build environment, wheel only needs manylinux1 symbols
    repaired_wheels = [fn for fn in filenames if policy in fn]
    assert repaired_wheels == ['hello-0.1.0-cp35-cp35m-{policy}_x86_64.whl'.format(policy=policy)]
    repaired_wheel = repaired_wheels[0]

    return repaired_wheel


def test_repair_reccurent_dependency(docker_container):
    # tests https://github.com/pypa/auditwheel/issues/136
    policy, manylinux_id, python_id, io_folder = docker_container
    orig_wheel = build_hello_wheel(docker_container)

    # attempting repair of the hello wheel
    repaired_wheel = repair_hello_wheel(orig_wheel, docker_container)

    output = docker_exec(manylinux_id, 'auditwheel show /io/' + repaired_wheel)
    # because this wheel is eligible to the manylinux1 tag, it will
    # actually prioritize manylinux1 instead of manylinux2010
    assert (
        'hello-0.1.0-cp35-cp35m-{policy}_x86_64.whl is consistent with the'
        'following platform tag: "manylinux1_x86_64"'
    ).format(policy=policy) in output.replace('\n', '')


def test_correct_rpath_hello_wheel(docker_container):
    # this tests https://github.com/pypa/auditwheel/issues/137
    policy, manylinux_id, python_id, io_folder = docker_container
    orig_wheel = build_hello_wheel(docker_container)

    # attempting repair of the hello wheel
    repaired_wheel = repair_hello_wheel(orig_wheel, docker_container)

    # Test whether repaired wheel is functioning.

    # TODO: Remove once pip supports manylinux2010
    docker_exec(
        python_id,
        "pip install git+https://github.com/wtolson/pip.git@manylinux2010",
    )

    test_commands = [
        'pip install -U /io/' + repaired_wheel,
        'python /auditwheel_src/tests/pr134/hello_module/tests/manual_test.py',
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
