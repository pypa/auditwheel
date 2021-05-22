#!/bin/bash

set -exuo pipefail

if [ "$(uname -m)" == "ppc64le" ]; then
    # We need to run a rootless docker daemon due to travis-ci LXD configuration
    # Update docker, c.f. https://developer.ibm.com/components/ibm-power/tutorials/install-docker-on-linux-on-power/
    sudo systemctl stop docker
    sudo apt-get update
    sudo apt-get remove -y docker docker.io containerd runc
    sudo apt-get install -y --no-install-recommends containerd uidmap slirp4netns fuse-overlayfs
    curl -fsSLO https://oplab9.parqtec.unicamp.br/pub/ppc64el/docker/version-20.10.6/ubuntu-focal/docker-ce-cli_20.10.6~3-0~ubuntu-focal_ppc64el.deb
    curl -fsSLO https://oplab9.parqtec.unicamp.br/pub/ppc64el/docker/version-20.10.6/ubuntu-focal/docker-ce_20.10.6~3-0~ubuntu-focal_ppc64el.deb
    curl -fsSLO https://oplab9.parqtec.unicamp.br/pub/ppc64el/docker/version-20.10.6/ubuntu-focal/docker-ce-rootless-extras_20.10.6~3-0~ubuntu-focal_ppc64el.deb
    # prevent the docker service to start upon installation
    echo -e '#!/bin/sh\nexit 101' | sudo tee /usr/sbin/policy-rc.d
    sudo chmod +x /usr/sbin/policy-rc.d
    # install docker
    sudo dpkg -i docker-ce-cli_20.10.6~3-0~ubuntu-focal_ppc64el.deb docker-ce-rootless-extras_20.10.6~3-0~ubuntu-focal_ppc64el.deb docker-ce_20.10.6~3-0~ubuntu-focal_ppc64el.deb
    # "restore" policy-rc.d
    sudo rm -f /usr/sbin/policy-rc.d
    # prepare & start the rootless docker daemon
    dockerd-rootless-setuptool.sh install --force
    export XDG_RUNTIME_DIR=/home/travis/.docker/run
    dockerd-rootless.sh &> /dev/null &
    DOCKERD_ROOTLESS_PID=$!
    echo "${DOCKERD_ROOTLESS_PID}" > ${HOME}/dockerd-rootless.pid
    docker context use rootless
fi

pip install -r test-requirements.txt
pip install tox codecov
pip install -e .
# pull manylinux images that will be used, this helps passing tests which would otherwise timeout.
python -c $'from tests.integration.test_manylinux import MANYLINUX_IMAGES\nfor image in MANYLINUX_IMAGES.values():\n    print(image)' | xargs -L 1 docker pull
