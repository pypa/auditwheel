from importlib import metadata
from pathlib import Path
from unittest.mock import call, patch

import pytest

from auditwheel._vendor.whichprovides import ProvidedBy
from auditwheel.sboms import create_sbom_for_wheel


def test_invalid_wheel_fname():
    with pytest.raises(ValueError, match="Failed to parse wheel file name"):
        create_sbom_for_wheel("not-a-wheel", [Path("path")])


@patch("auditwheel.sboms.whichprovides")
def test_create_sbom(whichprovides):
    whichprovides.return_value = {
        "path": ProvidedBy(
            package_type="deb",
            package_name="python3",
            package_version="3.10.6",
            distro="ubuntu",
        ),
    }

    auditwheel_version = metadata.version("auditwheel")
    wheel_fname = "testpackage-0.0.1-py3-none-any.whl"
    sbom = create_sbom_for_wheel(wheel_fname, [Path("path")])

    assert whichprovides.call_args_list == [call(["path"])]
    assert sbom == {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "version": 1,
        "metadata": {
            "component": {
                "type": "library",
                "bom-ref": f"pkg:pypi/testpackage@0.0.1?file_name={wheel_fname}",
                "name": "testpackage",
                "version": "0.0.1",
                "purl": f"pkg:pypi/testpackage@0.0.1?file_name={wheel_fname}",
            },
            "tools": [{"name": "auditwheel", "version": auditwheel_version}],
        },
        "components": [
            {
                "type": "library",
                "bom-ref": f"pkg:pypi/testpackage@0.0.1?file_name={wheel_fname}",
                "name": "testpackage",
                "version": "0.0.1",
                "purl": f"pkg:pypi/testpackage@0.0.1?file_name={wheel_fname}",
            },
            {
                "type": "library",
                "bom-ref": "pkg:deb/ubuntu/python3@3.10.6#a0af9f865bf637e6736817f4ce552e4cdf7b8c36ea75bc254c1d1f0af744b5bf",  # noqa: E501
                "name": "python3",
                "version": "3.10.6",
                "purl": "pkg:deb/ubuntu/python3@3.10.6",
            },
        ],
        "dependencies": [
            {
                "ref": f"pkg:pypi/testpackage@0.0.1?file_name={wheel_fname}",
                "dependsOn": [
                    "pkg:deb/ubuntu/python3@3.10.6#a0af9f865bf637e6736817f4ce552e4cdf7b8c36ea75bc254c1d1f0af744b5bf",
                ],
            },
            {
                "ref": "pkg:deb/ubuntu/python3@3.10.6#a0af9f865bf637e6736817f4ce552e4cdf7b8c36ea75bc254c1d1f0af744b5bf",  # noqa: E501
            },
        ],
    }
