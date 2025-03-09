FROM --platform=linux/amd64 mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

RUN --mount=type=cache,target=/home/vscode/.cache/pip \
    set -eux; \
    apt-get update; \
    apt-get install -y moreutils; \
    pip wheel --no-deps torch; \
    pip install patchelf pre-commit nox ipdb torch-*.whl; \
    mkdir -p /usr/local/lib/nv; \
    ln -s /usr/local/lib/python3.12/site-packages/nvidia/*/lib/*.so* /usr/local/lib/nv/; \
    echo "/usr/local/lib/nv" > /etc/ld.so.conf.d/nv.conf; \
    ldconfig -p

COPY demo.sh /
