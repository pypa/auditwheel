set -e

# Download some other wheels that Nathaniel made
URL=https://vorpus.org/~njs/tmp/manylinux-test-wheels/original/
curl --silent $URL | grep 'a href' | grep whl | cut -d ' ' -f 8 | cut -d '=' -f 2 | cut -d '"' -f 2 | xargs -n1 -I '{}' wget --no-check-certificate -P wheelhouse-njs "$URL/{}"

# These are boring
rm -f wheelhouse*/*-none-any.whl

mkdir -p wheelhouse-ucs2
cp $(dirname "${BASH_SOURCE[0]}")/cffi-1.5.0-cp27-none-linux_x86_64.whl wheelhouse-ucs2/

for whl in wheelhouse*/*.whl; do
    echo '-----------------'
    auditwheel show $whl
    auditwheel repair $whl -w output/ || true

    if [ -f "output/$(basename $whl)" ]; then
        auditwheel show output/$(basename $whl)
    fi
done
