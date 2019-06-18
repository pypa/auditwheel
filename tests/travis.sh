#!/bin/bash

set -exo pipefail

if [[ "$WHEELHOUSE" == "1" ]]; then
    bash tests/test-wheelhouses.sh
elif [[ "$LINTER" == "1" ]]; then
    tox -e lint
else
    pytest -s --cov auditwheel
    auditwheel lddtree $(python -c 'import sys; print(sys.executable)')
    codecov || true  # Ignore failures from codecov tool
fi
