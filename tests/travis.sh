#!/bin/bash

set -exo pipefail

if [[ "$WHEELHOUSE" == "1" ]]; then
    bash tests/integration/test-wheelhouses.sh
else
    pytest -s
    auditwheel lddtree $(python -c 'import sys; print(sys.executable)')
fi
