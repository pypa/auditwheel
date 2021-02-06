#!/bin/bash

set -exuo pipefail

pip install -r test-requirements.txt
pip install tox codecov
pip install -e .
# pull manylinux images that will be used, this helps passing tests which would otherwise timeout.
python -c $'from tests.integration.test_manylinux import MANYLINUX_IMAGES\nfor image in MANYLINUX_IMAGES.values():\n    print(image)' | xargs -L 1 docker pull
