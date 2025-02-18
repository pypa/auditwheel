FROM mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

RUN --mount=type=cache,target=/home/vscode/.cache/pip \
    set -eux; \
    pip wheel --no-deps torch; \
    pip install patchelf torch-*.whl
