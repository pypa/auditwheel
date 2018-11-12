#!/bin/bash

set -exo pipefail

if [[ "$WHEELHOUSE" == "1" ]]; then
    bash tests/test-wheelhouses.sh
else
    # log-cli-level not currently supported by the pytest version used by the Python 3.4 build.
    pytest -s --log-cli-level=25 || ( echo "$(pytest --version)" && pytest -s --log-level=25 )
    auditwheel lddtree $(python -c 'import sys; print(sys.executable)')
fi
