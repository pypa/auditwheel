from subprocess import check_call, check_output, CalledProcessError
import pytest
import os
import os.path as op
import tempfile
import shutil
import warnings
from distutils.spawn import find_executable
import logging
from auditwheel.policy import get_priority_by_name


logger = logging.getLogger(__name__)


ENCODING = 'utf-8'
MANYLINUX1_IMAGE_ID = 'quay.io/pypa/manylinux1_x86_64'
MANYLINUX2010_IMAGE_ID = 'quay.io/pypa/manylinux2010_x86_64'
MANYLINUX_IMAGES = {
    'manylinux1': MANYLINUX1_IMAGE_ID,
    'manylinux2010': MANYLINUX2010_IMAGE_ID,
}
DOCKER_CONTAINER_NAME = 'auditwheel-test-manylinux'
PYTHON_IMAGE_ID = 'python:3.5'
DEVTOOLSET = {
    'manylinux1': 'devtoolset-2',
    'manylinux2010': 'devtoolset-8',
}
PATH_DIRS = [
    '/opt/python/cp35-cp35m/bin',
    '/opt/rh/{devtoolset}/root/usr/bin',
    '/usr/local/sbin',
    '/usr/local/bin',
    '/usr/sbin',
    '/usr/bin',
    '/sbin',
    '/bin',
]
PATH = {k: ':'.join(PATH_DIRS).format(devtoolset=v)
        for k, v in DEVTOOLSET.items()}
WHEEL_CACHE_FOLDER = op.expanduser('~/.cache/auditwheel_tests')
ORIGINAL_NUMPY_WHEEL = 'numpy-1.11.0-cp35-cp35m-linux_x86_64.whl'
ORIGINAL_SIX_WHEEL = 'six-1.11.0-py2.py3-none-any.whl'


def find_src_folder():
    candidate = op.abspath(op.join(op.dirname(__file__), '../..'))
    contents = os.listdir(candidate)
    if 'setup.py' in contents and 'auditwheel' in contents:
        return candidate


def docker_start(image, volumes={}, env_variables={}):
    """Start a long waiting idle program in container

    Return the container id to be used for 'docker exec' commands.
    """
    # Make sure to use the latest public version of the docker image
    cmd = ['docker', 'pull', image]
    logger.info("$ " + " ".join(cmd))
    output = check_output(cmd).decode(ENCODING).strip()
    logger.info(output)
    cmd = ['docker', 'run', '-d']
    for guest_path, host_path in sorted(volumes.items()):
        cmd.extend(['-v', '%s:%s' % (host_path, guest_path)])
    for name, value in sorted(env_variables.items()):
        cmd.extend(['-e', '%s=%s' % (name, value)])
    cmd.extend([image, 'sleep', '10000'])
    logger.info("$ " + " ".join(cmd))
    return check_output(cmd).decode(ENCODING).strip()


def docker_exec(container_id, cmd):
    """Executed a command in the runtime context of a running container."""
    if isinstance(cmd, str):
        cmd = cmd.split()
    cmd = ['docker', 'exec', container_id] + cmd
    logger.info("$ " + " ".join(cmd))
    output = check_output(cmd).decode(ENCODING)
    logger.info(output)
    return output


@pytest.fixture(params=MANYLINUX_IMAGES.keys())
def docker_container(request):
    if find_executable("docker") is None:
        pytest.skip('docker is required')

    policy = request.param
    if not op.exists(op.join(WHEEL_CACHE_FOLDER, policy)):
        os.makedirs(op.join(WHEEL_CACHE_FOLDER, policy))
    src_folder = find_src_folder()
    if src_folder is None:
        pytest.skip('Can only be run from the source folder')
    io_folder = tempfile.mkdtemp(prefix='tmp_auditwheel_test_manylinux_',
                                 dir=src_folder)

    manylinux_id, python_id = None, None
    try:
        # Launch a docker container with volumes and pre-configured Python
        # environment. The container main program will just sleep. Commands
        # can be executed in that environment using the 'docker exec'.
        # This container will be used to build and repair manylinux compatible
        # wheels
        manylinux_id = docker_start(
            MANYLINUX_IMAGES[policy],
            volumes={'/io': io_folder, '/auditwheel_src': src_folder},
            env_variables={'PATH': PATH[policy]})
        # Install the development version of auditwheel from source:
        docker_exec(manylinux_id, 'pip install -U pip setuptools')
        docker_exec(manylinux_id, 'pip install -U /auditwheel_src')

        # Launch a docker container with a more recent userland to check that
        # the generated wheel can install and run correctly.
        python_id = docker_start(
            PYTHON_IMAGE_ID,
            volumes={'/io': io_folder, '/auditwheel_src': src_folder})
        docker_exec(python_id, 'pip install -U pip')
        yield policy, manylinux_id, python_id, io_folder
    finally:
        for container_id in [manylinux_id, python_id]:
            if container_id is None:
                continue
            try:
                check_call(['docker', 'rm', '-f', container_id])
            except CalledProcessError:
                warnings.warn('failed to terminate and delete container %s'
                              % container_id)
        shutil.rmtree(io_folder)


def test_build_repair_numpy(docker_container):
    # Integration test repair numpy built from scratch

    # First build numpy from source as a naive linux wheel that is tied
    # to system libraries (atlas, libgfortran...)
    policy, manylinux_id, python_id, io_folder = docker_container
    docker_exec(manylinux_id, 'yum install -y atlas atlas-devel')

    if op.exists(op.join(WHEEL_CACHE_FOLDER, policy, ORIGINAL_NUMPY_WHEEL)):
        # If numpy has already been built and put in cache, let's reuse this.
        shutil.copy2(op.join(WHEEL_CACHE_FOLDER, policy, ORIGINAL_NUMPY_WHEEL),
                     op.join(io_folder, ORIGINAL_NUMPY_WHEEL))
    else:
        # otherwise build the original linux_x86_64 numpy wheel from source
        # and put the result in the cache folder to speed-up future build.
        # This part of the build is independent of the auditwheel code-base
        # so it's safe to put it in cache.
        docker_exec(manylinux_id,
                    'pip wheel -w /io --no-binary=:all: numpy==1.11.0')
        shutil.copy2(op.join(io_folder, ORIGINAL_NUMPY_WHEEL),
                     op.join(WHEEL_CACHE_FOLDER, policy, ORIGINAL_NUMPY_WHEEL))
    filenames = os.listdir(io_folder)
    assert filenames == [ORIGINAL_NUMPY_WHEEL]
    orig_wheel = filenames[0]
    assert 'manylinux' not in orig_wheel

    # Repair the wheel using the manylinux container
    repair_command = (
        'auditwheel repair --plat {policy}_x86_64 -w /io /io/{orig_wheel}'
    ).format(policy=policy, orig_wheel=orig_wheel)
    docker_exec(manylinux_id, repair_command)
    filenames = os.listdir(io_folder)

    assert len(filenames) == 2
    repaired_wheels = [fn for fn in filenames if 'manylinux' in fn]
    assert repaired_wheels == ['numpy-1.11.0-cp35-cp35m-{}_x86_64.whl'.format(policy)]
    repaired_wheel = repaired_wheels[0]
    output = docker_exec(manylinux_id, 'auditwheel show /io/' + repaired_wheel)
    assert (
        'numpy-1.11.0-cp35-cp35m-{policy}_x86_64.whl is consistent'
        ' with the following platform tag: "{policy}_x86_64"'
    ).format(policy=policy) in output.replace('\n', ' ')

    # Check that the repaired numpy wheel can be installed and executed
    # on a modern linux image.
    docker_exec(python_id, 'pip install /io/' + repaired_wheel)
    output = docker_exec(
        python_id,
        'python /auditwheel_src/tests/integration/quick_check_numpy.py').strip()
    assert output.strip() == 'ok'

    # Check that numpy f2py works with a more recent version of gfortran
    docker_exec(python_id, 'apt-get update -yqq')
    docker_exec(python_id, 'apt-get install -y gfortran')
    docker_exec(python_id, 'python -m numpy.f2py'
                           ' -c /auditwheel_src/tests/integration/foo.f90 -m foo')

    # Check that the 2 fortran runtimes are well isolated and can be loaded
    # at once in the same Python program:
    docker_exec(python_id, ["python", "-c", "'import numpy; import foo'"])


def test_build_wheel_with_binary_executable(docker_container):
    # Test building a wheel that contains a binary executable (e.g., a program)

    policy, manylinux_id, python_id, io_folder = docker_container
    docker_exec(manylinux_id, 'yum install -y gsl-devel')

    docker_exec(manylinux_id, ['bash', '-c', 'cd /auditwheel_src/tests/integration/testpackage && python -m pip wheel --no-deps -w /io .'])

    filenames = os.listdir(io_folder)
    assert filenames == ['testpackage-0.0.1-py3-none-any.whl']
    orig_wheel = filenames[0]
    assert 'manylinux' not in orig_wheel

    # Repair the wheel using the appropriate manylinux container
    repair_command = (
        'auditwheel repair --plat {policy}_x86_64 -w /io /io/{orig_wheel}'
    ).format(policy=policy, orig_wheel=orig_wheel)
    docker_exec(manylinux_id, repair_command)
    filenames = os.listdir(io_folder)
    assert len(filenames) == 2
    repaired_wheels = [fn for fn in filenames if policy in fn]
    # Wheel picks up newer symbols when built in manylinux2010
    expected_wheel_name = 'testpackage-0.0.1-py3-none-%s_x86_64.whl' % policy
    assert repaired_wheels == [expected_wheel_name]
    repaired_wheel = repaired_wheels[0]
    output = docker_exec(manylinux_id, 'auditwheel show /io/' + repaired_wheel)
    assert (
        'testpackage-0.0.1-py3-none-{policy}_x86_64.whl is consistent'
        ' with the following platform tag: "{policy}_x86_64"'
    ).format(policy=policy) in output.replace('\n', ' ')

    docker_exec(python_id, 'pip install /io/' + repaired_wheel)
    output = docker_exec(
        python_id, ['python', '-c', 'from testpackage import runit; print(runit(1.5))']).strip()
    assert output.strip() == '2.25'

@pytest.mark.parametrize('with_dependency', ['0', '1'])
def test_build_wheel_with_highest_policy_and_image_dependencies(with_dependency, docker_container):
    # try to repair the wheel targeting different policies
    #
    # with_dependency == 0
    #   The python module has no dependencies that should be grafted-in and
    #   uses versioned symbols not available on policies pre-dating the policy matching the image being tested.
    # with_dependency == 1
    #   The python module itself does not use versioned symbols but has a dependency that should be grafted-in that
    #   uses versioned symbols not available on policies pre-dating the policy matching the image being tested.

    policy, manylinux_id, python_id, io_folder = docker_container

    docker_exec(manylinux_id, ['bash', '-c', 'cd /auditwheel_src/tests/testdependencies && WITH_DEPENDENCY={} python setup.py -v build_ext -f bdist_wheel -d /io'.format(with_dependency)])

    filenames = os.listdir(io_folder)
    orig_wheel = filenames[0]
    assert 'manylinux' not in orig_wheel

    repair_command = 'LD_LIBRARY_PATH=/auditwheel_src/tests/testdependencies auditwheel -v repair --plat {policy}_x86_64 -w /io /io/{orig_wheel}'

    older_policies = [p for p in MANYLINUX_IMAGES.keys() if get_priority_by_name(policy + '_x86_64') < get_priority_by_name(p + '_x86_64')]
    for target_policy in older_policies:
        # we shall fail to repair the wheel when targeting an older policy than the one matching the image
        with pytest.raises(CalledProcessError):
            docker_exec(manylinux_id, ['bash', '-c', repair_command.format(policy=target_policy, orig_wheel=orig_wheel)])

    # go-on checking all works properly when targeting the policy matching the image
    docker_exec(manylinux_id, ['bash', '-c', repair_command.format(policy=policy, orig_wheel=orig_wheel)])
    filenames = os.listdir(io_folder)
    assert len(filenames) == 2
    repaired_wheels = [fn for fn in filenames if policy in fn]
    expected_wheel_name = 'testdependencies-0.0.1-cp35-cp35m-%s_x86_64.whl' % policy
    assert repaired_wheels == [expected_wheel_name]
    repaired_wheel = repaired_wheels[0]
    output = docker_exec(manylinux_id, 'auditwheel show /io/' + repaired_wheel)
    assert (
        'testdependencies-0.0.1-cp35-cp35m-{policy}_x86_64.whl is consistent'
        ' with the following platform tag: "{policy}_x86_64"'
    ).format(policy=policy) in output.replace('\n', ' ')

    # check the orignal wheel with a dependency was not compliant
    # and check the one without a dependency was already compliant
    output = docker_exec(manylinux_id, 'auditwheel show /io/' + orig_wheel)
    if with_dependency == '1':
        assert (
            '{orig_wheel} is consistent with the following platform tag: "linux_x86_64"'
        ).format(orig_wheel=orig_wheel) in output.replace('\n', ' ')
    else:
        assert (
            '{orig_wheel} is consistent with the following platform tag: "{policy}_x86_64"'
        ).format(orig_wheel=orig_wheel, policy=policy) in output.replace('\n', ' ')

    docker_exec(python_id, 'pip install /io/' + repaired_wheel)
    output = docker_exec(
        python_id, ['python', '-c', 'from sys import exit; from testdependencies import run; exit(run())']).strip()


def test_build_repair_pure_wheel(docker_container):
    policy, manylinux_id, python_id, io_folder = docker_container

    if op.exists(op.join(WHEEL_CACHE_FOLDER, policy, ORIGINAL_SIX_WHEEL)):
        # If six has already been built and put in cache, let's reuse this.
        shutil.copy2(op.join(WHEEL_CACHE_FOLDER, policy,  ORIGINAL_SIX_WHEEL),
                     op.join(io_folder, ORIGINAL_SIX_WHEEL))
    else:
        docker_exec(manylinux_id,
                    'pip wheel -w /io --no-binary=:all: six==1.11.0')
        shutil.copy2(op.join(io_folder, ORIGINAL_SIX_WHEEL),
                     op.join(WHEEL_CACHE_FOLDER, policy, ORIGINAL_SIX_WHEEL))

    filenames = os.listdir(io_folder)
    assert filenames == [ORIGINAL_SIX_WHEEL]
    orig_wheel = filenames[0]
    assert 'manylinux' not in orig_wheel

    # Repair the wheel using the manylinux container
    repair_command = (
        'auditwheel repair --plat {policy}_x86_64 -w /io /io/{orig_wheel}'
    ).format(policy=policy, orig_wheel=orig_wheel)
    docker_exec(manylinux_id, repair_command)
    filenames = os.listdir(io_folder)
    assert len(filenames) == 1  # no new wheels
    assert filenames == [ORIGINAL_SIX_WHEEL]

    output = docker_exec(manylinux_id, 'auditwheel show /io/' + filenames[0])
    assert ''.join([
        ORIGINAL_SIX_WHEEL,
        ' is consistent with the following platform tag: ',
        '"manylinux1_x86_64".  ',
        'The wheel references no external versioned symbols from system- ',
        'provided shared libraries.  ',
        'The wheel requires no external shared libraries! :)',
    ]) in output.replace('\n', ' ')
