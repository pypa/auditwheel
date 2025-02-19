auditwheel -v repair \
    --exclude libcuds.so.1 \
    --exclude libcusolver.so.11 \
    --exclude libcusparseLt.so.0 \
    --plat=manylinux_2_35_x86_64 \
    /torch-2.6.0-cp312-cp312-manylinux1_x86_64.whl
