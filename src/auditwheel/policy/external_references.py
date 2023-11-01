from __future__ import annotations

import logging
import re
from typing import Any, Generator

from ..elfutils import filter_undefined_symbols, is_subdir
from . import WheelPolicies

log = logging.getLogger(__name__)
LIBPYTHON_RE = re.compile(r"^libpython\d+\.\d+m?.so(.\d)*$")


def lddtree_external_references(wheel_policies: list, lddtree: dict, wheel_path: str) -> dict:
    # XXX: Document the lddtree structure, or put it in something
    # more stable than a big nested dict
    def filter_libs(libs: set[str], whitelist: set[str]) -> Generator[str, None, None]:
        for lib in libs:
            if "ld-linux" in lib or lib in ["ld64.so.2", "ld64.so.1"]:
                # always exclude ELF dynamic linker/loader
                # 'ld64.so.2' on s390x
                # 'ld64.so.1' on ppc64le
                # 'ld-linux*' on other platforms
                continue
            if LIBPYTHON_RE.match(lib):
                # always exclude libpythonXY
                continue
            if lib in whitelist:
                # exclude any libs in the whitelist
                continue
            yield lib

    def get_req_external(libs: set[str], whitelist: set[str]) -> set[str]:
        # get all the required external libraries
        libs = libs.copy()
        reqs = set()
        while libs:
            lib = libs.pop()
            reqs.add(lib)
            for dep in filter_libs(lddtree["libs"][lib]["needed"], whitelist):
                if dep not in reqs:
                    libs.add(dep)
        return reqs

    ret: dict[str, dict[str, Any]] = {}
    for p in wheel_policies:
        needed_external_libs: set[str] = set()
        blacklist = {}

        if not (p["name"] == "linux" and p["priority"] == 0):
            # special-case the generic linux platform here, because it
            # doesn't have a whitelist. or, you could say its
            # whitelist is the complete set of all libraries. so nothing
            # is considered "external" that needs to be copied in.
            whitelist = set(p["lib_whitelist"])
            blacklist_libs = set(p["blacklist"].keys()) & set(lddtree["needed"])
            blacklist = {k: p["blacklist"][k] for k in blacklist_libs}
            blacklist = filter_undefined_symbols(lddtree["realpath"], blacklist)
            needed_external_libs = get_req_external(
                set(filter_libs(lddtree["needed"], whitelist)), whitelist
            )

        pol_ext_deps = {}
        for lib in needed_external_libs:
            if is_subdir(lddtree["libs"][lib]["realpath"], wheel_path):
                # we didn't filter libs that resolved via RPATH out
                # earlier because we wanted to make sure to pick up
                # our elf's indirect dependencies. But now we want to
                # filter these ones out, since they're not "external".
                log.debug("RPATH FTW: %s", lib)
                continue
            pol_ext_deps[lib] = lddtree["libs"][lib]["realpath"]
        ret[p["name"]] = {
            "libs": pol_ext_deps,
            "priority": p["priority"],
            "blacklist": blacklist,
        }
    return ret
