import os
import shutil
import sys

import pytest
from auditwheel.repair import copylib
from auditwheel.tmpdirs import InTemporaryDirectory
from auditwheel.lddtree import lddtree

@pytest.fixture
def systemlib():
    for libdata in lddtree(sys.executable)["libs"].values():
        # return one of the arbitrary libraries that python is linked
        # against, like libc.so.6. any one will do.         
        return libdata["realpath"]


on_supported_platform = pytest.mark.skipif(
    sys.platform != 'linux', reason="requires Linux system"
)

@on_supported_platform
def test_copylib(systemlib):
    with InTemporaryDirectory():
        copylib(systemlib, "./")
        contents = os.listdir(".")
        assert len(contents) == 1


@on_supported_platform
def test_copylib_readonly(systemlib):
    # Confirm fix of auditwheel#237
    with InTemporaryDirectory():        
        localname = os.path.basename(systemlib)
        # copy the file into the tempdir before setting it to read only
        # and then ensure that `copylib` still works
        shutil.copy(systemlib, localname)
        os.chmod(localname, 0o444)
        os.mkdir("dest_dir")
        copylib(localname, "dest_dir/")
        assert len(os.listdir("dest_dir")) == 1
