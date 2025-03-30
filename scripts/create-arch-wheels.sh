#!/bin/sh

# This script is used to create wheels for unsupported architectures
# in order to extend coverage and check errors with those.

set -eux

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)"
INTEGRATION_TEST_DIR="${SCRIPT_DIR}/../tests/integration"
mkdir -p "${INTEGRATION_TEST_DIR}/arch-wheels/glibc"
mkdir -p "${INTEGRATION_TEST_DIR}/arch-wheels/musllinux_1_2"

# "mips64le" built with buildpack-deps:bookworm and renamed cp313-cp313
for ARCH in  "386" "amd64" "arm/v5" "arm/v7" "arm64/v8" "ppc64le" "riscv64" "s390x"; do
  docker run --platform linux/${ARCH} -i --rm -v "${INTEGRATION_TEST_DIR}:/tests" debian:trixie-20250203 << "EOF"
# for, "arm/v5" QEMU will report armv7l, running on aarch64 will report aarch64, force armv5l/armv7l
case "$(dpkg --print-architecture)" in
  armel) export _PYTHON_HOST_PLATFORM="linux-armv5l";;
  armhf) export _PYTHON_HOST_PLATFORM="linux-armv7l";;
  *) ;;
esac
DEBIAN_FRONTEND=noninteractive apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gcc python3-pip python3-dev
python3 -m pip wheel --no-deps -w /tests/arch-wheels/glibc /tests/testsimple
EOF
done

for ARCH in "386" "amd64" "arm/v6" "arm/v7" "arm64/v8" "ppc64le" "riscv64" "s390x"; do
  docker run --platform linux/${ARCH} -i --rm -v "${INTEGRATION_TEST_DIR}:/tests" alpine:3.21 << "EOF"
# for, "arm/v5" QEMU will report armv7l, running on aarch64 will report aarch64, force armv5l/armv7l
case "$(cat /etc/apk/arch)" in
  armhf) export _PYTHON_HOST_PLATFORM="linux-armv6l";;
  armv7) export _PYTHON_HOST_PLATFORM="linux-armv7l";;
  *) ;;
esac
apk add gcc binutils musl-dev python3-dev py3-pip
python3 -m pip wheel --no-deps -w /tests/arch-wheels/musllinux_1_2 /tests/testsimple
EOF
done
