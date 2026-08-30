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


@patch("auditwheel.sboms.whichprovides")
def test_create_sbom_component_order_is_deterministic(whichprovides):
    # Two .so files from the same RPM package (identical purl), reproducing
    # the CUDA build case (libcublas.so.13 and libcublas.so.13.1.1.3 both
    # come from libcublas-13-0).
    libcublas = ProvidedBy(
        package_type="rpm",
        package_name="libcublas",
        package_version="13.1.1.3-1",
        distro="almalinux",
    )
    wheel_fname = "testpackage-0.0.1-py3-none-any.whl"

    whichprovides.return_value = {
        "/lib/libcublas.so.13": libcublas,
        "/lib/libcublas.so.13.1.1.3": libcublas,
    }
    sbom_a = create_sbom_for_wheel(
        wheel_fname,
        [Path("/lib/libcublas.so.13"), Path("/lib/libcublas.so.13.1.1.3")],
    )

    # Different insertion order (e.g. different PYTHONHASHSEED). Since purl
    # is identical for both files, only the filepath tie-break keeps this
    # deterministic.
    whichprovides.return_value = {
        "/lib/libcublas.so.13.1.1.3": libcublas,
        "/lib/libcublas.so.13": libcublas,
    }
    sbom_b = create_sbom_for_wheel(
        wheel_fname,
        [Path("/lib/libcublas.so.13.1.1.3"), Path("/lib/libcublas.so.13")],
    )

    assert sbom_a is not None
    assert sbom_a == sbom_b

    bom_refs = [c["bom-ref"] for c in sbom_a["components"][1:]]
    assert bom_refs == sorted(bom_refs)
