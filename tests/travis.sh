#!/bin/bash

set -exo pipefail

if [[ "$LINTER" == "1" ]]; then
    tox -e lint
else
    pytest -s --cov auditwheel --cov-branch
    auditwheel lddtree $(python -c 'import sys; print(sys.executable)')
    codecov || true  # Ignore failures from codecov tool
fi
