from __future__ import annotations

import hashlib
import typing
from importlib import metadata
from typing import TYPE_CHECKING
from urllib.parse import quote

from auditwheel._vendor.whichprovides import whichprovides
from auditwheel.wheeltools import WHEEL_INFO_RE

if TYPE_CHECKING:
    from pathlib import Path


def create_sbom_for_wheel(
    wheel_fname: str, sbom_filepaths: list[Path]
) -> None | dict[str, typing.Any]:
    # If there aren't any files then we bail.
    if not sbom_filepaths:
        return None

    # Pull the top-level package name and version
    # from the wheel filename. This segment doesn't
    # change even after "repairing", so we don't have
    # to worry about it changing.
    match = WHEEL_INFO_RE(wheel_fname)
    if not match:
        msg = f"Failed to parse wheel file name: {wheel_fname}"
        raise ValueError(msg)
    wheel_name = match.group("name")
    wheel_version = match.group("ver")
    wheel_purl = (
        f"pkg:pypi/{quote(wheel_name, safe='')}@{quote(wheel_version, safe='')}"
        f"?file_name={quote(wheel_fname, safe='')}"
    )

    # Lookup which packages provided libraries.
    # If there aren't any then we don't generate an SBOM.
    sbom_packages = whichprovides([str(f) for f in sbom_filepaths])
    if not sbom_packages:
        return None

    sbom_components: list[dict[str, typing.Any]] = [
        {
            "type": "library",
            "bom-ref": wheel_purl,
            "name": wheel_name,
            "version": wheel_version,
            "purl": wheel_purl,
        }
    ]
    sbom_dependencies = [{"ref": wheel_purl, "dependsOn": []}]
    sbom_data = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "version": 1,
        "metadata": {
            "component": sbom_components[0],
            "tools": [
                {"name": "auditwheel", "version": metadata.version("auditwheel")}
            ],
        },
        # These are mutated below through the variables.
        "components": sbom_components,
        "dependencies": sbom_dependencies,
    }

    for filepath, provided_by in sbom_packages.items():
        bom_ref = (
            provided_by.purl
            + f"#{hashlib.sha256(filepath.encode(errors='ignore')).hexdigest()}"
        )
        sbom_components.append(
            {
                "type": "library",
                "bom-ref": bom_ref,
                "name": provided_by.package_name,
                "version": provided_by.package_version,
                "purl": provided_by.purl,
            }
        )
        sbom_dependencies[0]["dependsOn"].append(bom_ref)  # type: ignore[attr-defined]
        sbom_dependencies.append({"ref": bom_ref})

    return sbom_data
