from __future__ import annotations

import os
import subprocess
import sysconfig
from importlib.metadata import distribution


def runit(x):
    dist = distribution("testpackage")
    scripts_paths = [
        os.path.abspath(sysconfig.get_path("scripts", scheme))
        for scheme in sysconfig.get_scheme_names()
    ]
    scripts = []
    for file in dist.files:
        if os.path.abspath(str(file.locate().parent)) in scripts_paths:
            scripts.append(file.locate().resolve(strict=True))
    assert len(scripts) == 2, scripts
    filename = next(script for script in scripts if script.stem == "testprogram")
    output = subprocess.check_output([filename, str(x)])
    return float(output)
