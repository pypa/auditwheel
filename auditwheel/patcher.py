import logging
import platform
import re
from collections import OrderedDict
from distutils.spawn import find_executable
from os.path import abspath, dirname, isabs
from subprocess import check_call, check_output, CalledProcessError

from .elfutils import is_subdir

logger = logging.getLogger(__name__)


class ElfPatcher:
    def replace_needed(self,
                       file_name: str,
                       so_name: str,
                       new_so_name: str) -> None:
        raise NotImplementedError

    def set_soname(self,
                   file_name: str,
                   new_so_name: str) -> None:
        raise NotImplementedError

    def set_rpath(self,
                  file_name: str,
                  rpath: str) -> None:
        raise NotImplementedError

    def get_rpath(self,
                  file_name: str) -> str:
        raise NotImplementedError

    def append_rpath(self,
                     file_name: str,
                     rpath: str,
                     wheel_base_dir: str) -> None:
        raise NotImplementedError


def _verify_patchelf() -> None:
    """This function looks for the ``patchelf`` external binary in the PATH,
    checks for the required version, and throws an exception if a proper
    version can't be found. Otherwise, silcence is golden
    """
    if not find_executable('patchelf'):
        raise ValueError('Cannot find required utility `patchelf` in PATH')
    try:
        version = check_output(['patchelf', '--version']).decode("utf-8")
    except CalledProcessError:
        raise ValueError('Could not call `patchelf` binary')

    m = re.match(r'patchelf\s+(\d+(.\d+)?)', version)
    if m and tuple(int(x) for x in m.group(1).split('.')) >= (0, 9):
        return
    raise ValueError(('patchelf %s found. auditwheel repair requires '
                      'patchelf >= 0.9.') %
                     version)


class Patchelf(ElfPatcher):
    def __init__(self):
        _verify_patchelf()

    def replace_needed(self,
                       file_name: str,
                       so_name: str,
                       new_so_name: str) -> None:
        check_call(['patchelf', '--replace-needed', so_name, new_so_name,
                    file_name])

    def set_soname(self,
                   file_name: str,
                   new_so_name: str) -> None:
        check_call(['patchelf', '--set-soname', new_so_name, file_name])

    def set_rpath(self,
                  file_name: str,
                  rpath: str) -> None:

        check_call(['patchelf', '--remove-rpath', file_name])
        check_call(['patchelf', '--force-rpath', '--set-rpath',
                    rpath, file_name])

    def get_rpath(self,
                  file_name: str) -> str:

        return check_output(['patchelf', '--print-rpath',
                             file_name]).decode('utf-8').strip()

    def append_rpath(self,
                     file_name: str,
                     rpath: str,
                     wheel_base_dir: str) -> None:
        """Add a new rpath entry to a file while preserving as many existing
        rpath entries as possible.

        In order to preserve an rpath entry it must:

        1) Point to a location within wheel_base_dir.
        2) Not be a duplicate of an already-existing rpath entry.
        """
        old_rpaths = self.get_rpath(file_name)
        old_rpaths = _preserve_existing_rpaths(old_rpaths, file_name,
                                               wheel_base_dir)
        if old_rpaths != '':
            if rpath not in old_rpaths.split(':'):
                rpath = ':'.join([old_rpaths, rpath])
            else:
                rpath = old_rpaths
        self.set_rpath(file_name, rpath)


def _preserve_existing_rpaths(rpaths: str,
                              lib_name: str,
                              wheel_base_dir: str) -> str:

    if not isabs(lib_name):
        lib_name = abspath(lib_name)
    lib_dir = dirname(lib_name)
    if not isabs(wheel_base_dir):
        wheel_base_dir = abspath(wheel_base_dir)

    new_rpaths = OrderedDict()  # Use this to fake an OrderedSet
    for rpath_entry in rpaths.split(':'):
        full_rpath_entry = _resolve_rpath_tokens(rpath_entry, lib_dir)
        if not isabs(full_rpath_entry):
            logger.debug('rpath entry {} could not be resolved to an absolute '
                         'path -- discarding it.'.format(rpath_entry))
            continue

        if is_subdir(full_rpath_entry, wheel_base_dir):
            logger.debug('Preserved rpath entry {}'.format(rpath_entry))
            new_rpaths[rpath_entry] = ''
        else:
            logger.debug('Rejected rpath entry {}'.format(rpath_entry))

    return ':'.join(new_rpaths.keys())


def _resolve_rpath_tokens(rpath: str,
                          lib_base_dir: str) -> str:
    # See https://www.man7.org/linux/man-pages/man8/ld.so.8.html#DESCRIPTION
    if platform.architecture()[0] == '64bit':
        system_lib_dir = 'lib64'
    else:
        system_lib_dir = 'lib'
    system_processor_type = platform.machine()
    token_replacements = {'ORIGIN': lib_base_dir,
                          'LIB': system_lib_dir,
                          'PLATFORM': system_processor_type}
    for token, target in token_replacements.items():
        rpath = rpath.replace('${}'.format(token), target)      # $TOKEN
        rpath = rpath.replace('${{{}}}'.format(token), target)  # ${TOKEN}
    return rpath
