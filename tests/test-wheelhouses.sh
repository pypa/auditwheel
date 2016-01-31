set -e

# Download some wheels from one location
PY_VERS="2.7 3.3 3.4 3.5"
for PYVER in ${PY_VERS}; do
    wget "https://github.com/getnikola/wheelhouse/archive/v${PYVER}.zip"
    unzip "v${PYVER}.zip"
done

# Download some other wheels that Nathaniel made
URL=https://vorpus.org/~njs/tmp/manylinux-test-wheels/original/
curl --silent $URL | grep 'a href' | grep whl | cut -d ' ' -f 8 | cut -d '=' -f 2 | cut -d '"' -f 2 | xargs -n1 -I '{}' wget --no-check-certificate -P wheelhouse-njs "$URL/{}"

# Download some more wheels that Robert made
URL=http://stanford.edu/~rmcgibbo/wheelhouse/
curl --silent $URL | grep 'a href' | grep whl | cut -d ' ' -f 8 | cut -d '=' -f 2 | cut -d '"' -f 2 | xargs -n1 -I '{}' wget -P wheelhouse-rmcgibbo "$URL/{}"

# These are boring
rm -f wheelhouse*/*-none-any.whl

mkdir wheelhouse-usc2
cp $(dirname "${BASH_SOURCE[0]}")/cffi-1.5.0-cp27-none-linux_x86_64.whl wheelhouse-ucs2

for whl in wheelhouse*/*.whl; do
    echo '-----------------'
    auditwheel show $whl
    auditwheel repair $whl -w output/ || true

    if [ -f "output/$(basename $whl)" ]; then
        auditwheel show output/$(basename $whl)
    fi
done
