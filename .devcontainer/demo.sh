#! /bin/bash

rm -rf /tmp/wheelhouse

auditwheel -v repair \
    --exclude libcuda.so.1 \
    --exclude libcusolver.so.11 \
    --exclude libcusparseLt.so.0 \
    --plat=manylinux_2_35_x86_64 \
    -w /tmp/wheelhouse \
    /torch-2.6.0-cp312-cp312-manylinux1_x86_64.whl \
    2>&1 | ts '[%Y-%m-%d %H:%M:%S]'
