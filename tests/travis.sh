#!/bin/bash

set -exo pipefail

if [[ "$WHEELHOUSE" == "1" ]]; then
    bash tests/test-wheelhouses.sh
else
    pytest -s --log-cli-level=25
    auditwheel lddtree $(python -c 'import sys; print(sys.executable)')
fi
