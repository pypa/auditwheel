import os
import re
from distutils.spawn import find_executable
import logging
from subprocess import check_call, check_output, CalledProcessError

import lief

logger = logging.getLogger(__name__)


class ElfPatcher:
    def replace_needed(self, file_name, so_name, new_so_name):
        pass

    def set_so_name(self, file_name, new_so_name):
        pass

    def set_rpath(self, file_name, rpath):
        pass


def _verify_patchelf():
    """This function looks for the ``patchelf`` external binary in the PATH,
    checks for the required version, and throws an exception if a proper
    version can't be found. Otherwise, silcence is golden
    """
    if not find_executable('patchelf'):
        raise ValueError('Cannot find required utility `patchelf` in PATH')
    try:
        version = check_output(['patchelf', '--version']).decode('utf-8')
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

    def replace_needed(self, file_name, so_name, new_so_name):
        args = ['patchelf', '--replace-needed', so_name, new_so_name,
                file_name]
        logger.debug("Calling patchelf with args:", args)
        check_call(args)

    def set_so_name(self, file_name, new_so_name):
        args = ['patchelf', '--set-soname', new_so_name, file_name]
        logger.debug("Calling patchelf with args:", args)
        check_call(args)

    def set_rpath(self, file_name, libdir):
        args = ['patchelf', '--remove-rpath', file_name]
        logger.debug("Calling patchelf with args:", args)
        check_call(args)
        new_rpath = os.path.relpath(libdir, os.path.dirname(file_name))
        rpath = os.path.join('$ORIGIN', new_rpath)
        args = ['patchelf', '--force-rpath', '--set-rpath', rpath, file_name]
        logger.debug("Calling patchelf with args:", args)
        check_call(args)


class Lief(ElfPatcher):
    # TODO make context manager, save only when done with everything?
    def replace_needed(self, file_name, so_name, new_so_name):
        elf = lief.parse(file_name)
        for lib in elf.dynamic_entries:
            if lib.tag == lief.ELF.DYNAMIC_TAGS.NEEDED and lib.name == so_name:
                logger.info("Replacing needed library: %s with %s",
                            lib.name, new_so_name)
                lib.name = new_so_name
                elf.write(file_name)

    def set_so_name(self, file_name, new_so_name):
        # TODO error handling (target might not be a library)
        elf = lief.parse(file_name)
        soname = elf.get(lief.ELF.DYNAMIC_TAGS.SONAME)
        soname.name = new_so_name
        logger.info("Setting SONAME to %s", soname)
        elf.write(file_name)

    def set_rpath(self, file_name, libdir):
        rpath_libdir = os.path.relpath(libdir, os.path.dirname(file_name))
        new_rpath = os.path.join('$ORIGIN', rpath_libdir)
        elf = lief.parse(file_name)
        try:
            rpath = elf.get(lief.ELF.DYNAMIC_TAGS.RPATH)
            logger.info("Current RPATH: %s", rpath)
            rpath.name = new_rpath
        except lief.not_found:
            logger.info("No RPATH found, creating new entry")
            rpath = lief.ELF.DynamicEntryRpath()
            rpath.name = new_rpath
            elf.add(rpath)

        logger.info("Setting new RPATH: %s", rpath)
        elf.write(file_name)



