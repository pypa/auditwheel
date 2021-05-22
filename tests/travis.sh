#!/bin/bash

set -exuo pipefail

if [ "$(uname -m)" == "ppc64le" ]; then
    export DOCKER_HOST=unix://${HOME}/.docker/run/docker.sock
fi

pytest -s --cov auditwheel --cov-branch
auditwheel lddtree $(python -c 'import sys; print(sys.executable)')
codecov || true  # Ignore failures from codecov tool
