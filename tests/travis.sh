#!/bin/bash

set -exo pipefail

pytest -s --cov auditwheel --cov-branch
auditwheel lddtree $(python -c 'import sys; print(sys.executable)')
codecov || true  # Ignore failures from codecov tool
