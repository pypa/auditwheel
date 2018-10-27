from subprocess import check_call, check_output, CalledProcessError
import pytest
import os
import os.path as op
import tempfile
import shutil
import warnings
from distutils.spawn import find_executable

VERBOSE = True
ENCODING = 'utf-8'
MANYLINUX_IMAGE_ID = 'quay.io/pypa/manylinux1_x86_64'
DOCKER_CONTAINER_NAME = 'auditwheel-test-manylinux'
PYTHON_IMAGE_ID = 'python:3.5'
PATH = ('/opt/python/cp35-cp35m/bin:/opt/rh/devtoolset-2/root/usr/bin:'
        '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin')
WHEEL_CACHE_FOLDER = op.expanduser('~/.cache/auditwheel_tests')
ORIGINAL_NUMPY_WHEEL = 'numpy-1.11.0-cp35-cp35m-linux_x86_64.whl'
ORIGINAL_SIX_WHEEL = 'six-1.11.0-py2.py3-none-any.whl'


def find_src_folder():
    candidate = op.abspath(op.join(op.dirname(__file__), '..'))
    contents = os.listdir(candidate)
    if 'setup.py' in contents and 'auditwheel' in contents:
        return candidate


def docker_start(image, volumes={}, env_variables={}):
    """Start a long waiting idle program in container

    Return the container id to be used for 'docker exec' commands.
    """
    # Make sure to use the latest public version of the docker image
    cmd = ['docker', 'pull', image]
    if VERBOSE:
        print("$ " + " ".join(cmd))
    output = check_output(cmd).decode(ENCODING).strip()
    if VERBOSE:
        print(output)
    cmd = ['docker', 'run', '-d']
    for guest_path, host_path in sorted(volumes.items()):
        cmd.extend(['-v', '%s:%s' % (host_path, guest_path)])
    for name, value in sorted(env_variables.items()):
        cmd.extend(['-e', '%s=%s' % (name, value)])
    cmd.extend([image, 'sleep', '10000'])
    if VERBOSE:
        print("$ " + " ".join(cmd))
    return check_output(cmd).decode(ENCODING).strip()


def docker_exec(container_id, cmd):
    """Executed a command in the runtime context of a running container."""
    if isinstance(cmd, str):
        cmd = cmd.split()
    cmd = ['docker', 'exec', container_id] + cmd
    if VERBOSE:
        print("$ " + " ".join(cmd))
    output = check_output(cmd).decode(ENCODING)
    if VERBOSE:
        print(output)
    return output


@pytest.yield_fixture
def docker_container():
    if find_executable("docker") is None:
        pytest.skip('docker is required')
    if not op.exists(WHEEL_CACHE_FOLDER):
        os.makedirs(WHEEL_CACHE_FOLDER)
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
            MANYLINUX_IMAGE_ID,
            volumes={'/io': io_folder, '/auditwheel_src': src_folder},
            env_variables={'PATH': PATH})
        # Install the development version of auditwheel from source:
        docker_exec(manylinux_id, 'pip install -U pip setuptools')
        docker_exec(manylinux_id, 'pip install -U /auditwheel_src')

        # Launch a docker container with a more recent userland to check that
        # the generated wheel can install and run correctly.
        python_id = docker_start(
            PYTHON_IMAGE_ID,
            volumes={'/io': io_folder, '/auditwheel_src': src_folder})
        docker_exec(python_id, 'pip install -U pip')
        yield manylinux_id, python_id, io_folder
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
    manylinux_id, python_id, io_folder = docker_container
    docker_exec(manylinux_id, 'yum install -y atlas atlas-devel')

    if op.exists(op.join(WHEEL_CACHE_FOLDER, ORIGINAL_NUMPY_WHEEL)):
        # If numpy has already been built and put in cache, let's reuse this.
        shutil.copy2(op.join(WHEEL_CACHE_FOLDER, ORIGINAL_NUMPY_WHEEL),
                     op.join(io_folder, ORIGINAL_NUMPY_WHEEL))
    else:
        # otherwise build the original linux_x86_64 numpy wheel from source
        # and put the result in the cache folder to speed-up future build.
        # This part of the build is independent of the auditwheel code-base
        # so it's safe to put it in cache.
        docker_exec(manylinux_id,
                    'pip wheel -w /io --no-binary=:all: numpy==1.11.0')
        shutil.copy2(op.join(io_folder, ORIGINAL_NUMPY_WHEEL),
                     op.join(WHEEL_CACHE_FOLDER, ORIGINAL_NUMPY_WHEEL))
    filenames = os.listdir(io_folder)
    assert filenames == [ORIGINAL_NUMPY_WHEEL]
    orig_wheel = filenames[0]
    assert 'manylinux' not in orig_wheel

    # Repair the wheel using the manylinux1 container
    docker_exec(manylinux_id, 'auditwheel repair -w /io /io/' + orig_wheel)
    filenames = os.listdir(io_folder)
    assert len(filenames) == 2
    repaired_wheels = [fn for fn in filenames if 'manylinux1' in fn]
    assert repaired_wheels == ['numpy-1.11.0-cp35-cp35m-manylinux1_x86_64.whl']
    repaired_wheel = repaired_wheels[0]
    output = docker_exec(manylinux_id, 'auditwheel show /io/' + repaired_wheel)
    assert (
        'numpy-1.11.0-cp35-cp35m-manylinux1_x86_64.whl is consistent'
        ' with the following platform tag: "manylinux1_x86_64"'
    ) in output.replace('\n', ' ')

    # Check that the repaired numpy wheel can be installed and executed
    # on a modern linux image.
    docker_exec(python_id, 'pip install /io/' + repaired_wheel)
    output = docker_exec(
        python_id, 'python /auditwheel_src/tests/quick_check_numpy.py').strip()
    assert output.strip() == 'ok'

    # Check that numpy f2py works with a more recent version of gfortran
    docker_exec(python_id, 'apt-get update -yqq')
    docker_exec(python_id, 'apt-get install -y gfortran')
    docker_exec(python_id, 'python -m numpy.f2py'
                           '       -c /auditwheel_src/tests/foo.f90 -m foo')

    # Check that the 2 fortran runtimes are well isolated and can be loaded
    # at once in the same Python program:
    docker_exec(python_id, ["python", "-c", "'import numpy; import foo'"])


def test_build_wheel_with_binary_executable(docker_container):
    # Test building a wheel that contains a binary executable (e.g., a program)

    manylinux_id, python_id, io_folder = docker_container
    docker_exec(manylinux_id, 'yum install -y gsl-devel')

    docker_exec(manylinux_id, ['bash', '-c', 'cd /auditwheel_src/tests/testpackage && python setup.py bdist_wheel -d /io'])

    filenames = os.listdir(io_folder)
    assert filenames == ['testpackage-0.0.1-py3-none-any.whl']
    orig_wheel = filenames[0]
    assert 'manylinux' not in orig_wheel

    # Repair the wheel using the manylinux1 container
    docker_exec(manylinux_id, 'auditwheel repair -w /io /io/' + orig_wheel)
    filenames = os.listdir(io_folder)
    assert len(filenames) == 2
    repaired_wheels = [fn for fn in filenames if 'manylinux1' in fn]
    assert repaired_wheels == ['testpackage-0.0.1-py3-none-manylinux1_x86_64.whl']
    repaired_wheel = repaired_wheels[0]
    output = docker_exec(manylinux_id, 'auditwheel show /io/' + repaired_wheel)
    assert (
        'testpackage-0.0.1-py3-none-manylinux1_x86_64.whl is consistent'
        ' with the following platform tag: "manylinux1_x86_64"'
    ) in output.replace('\n', ' ')

    # Check that the repaired numpy wheel can be installed and executed
    # on a modern linux image.
    docker_exec(python_id, 'pip install /io/' + repaired_wheel)
    output = docker_exec(
        python_id, ['python', '-c', 'from testpackage import runit; print(runit(1.5))']).strip()
    assert output.strip() == '2.25'


def test_build_repair_pure_wheel(docker_container):
    manylinux_id, python_id, io_folder = docker_container

    if op.exists(op.join(WHEEL_CACHE_FOLDER, ORIGINAL_SIX_WHEEL)):
        # If six has already been built and put in cache, let's reuse this.
        shutil.copy2(op.join(WHEEL_CACHE_FOLDER, ORIGINAL_SIX_WHEEL),
                     op.join(io_folder, ORIGINAL_SIX_WHEEL))
    else:
        docker_exec(manylinux_id,
                    'pip wheel -w /io --no-binary=:all: six==1.11.0')
        shutil.copy2(op.join(io_folder, ORIGINAL_SIX_WHEEL),
                     op.join(WHEEL_CACHE_FOLDER, ORIGINAL_SIX_WHEEL))

    filenames = os.listdir(io_folder)
    assert filenames == [ORIGINAL_SIX_WHEEL]
    orig_wheel = filenames[0]
    assert 'manylinux' not in orig_wheel

    # Repair the wheel using the manylinux1 container
    docker_exec(manylinux_id, 'auditwheel repair -w /io /io/' + orig_wheel)
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
