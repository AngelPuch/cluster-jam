#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
    printf 'Ejecuta este aprovisionamiento como root.\n' >&2
    exit 1
fi

# shellcheck source=/dev/null
source /etc/os-release

if [[ "${ID}" != "ubuntu" || "${VERSION_ID}" != "24.04" ]]; then
    printf 'Este script requiere Ubuntu 24.04 LTS.\n' >&2
    exit 1
fi

docker_user="${DOCKER_USER:-vagrant}"
id "${docker_user}" >/dev/null

export DEBIAN_FRONTEND=noninteractive

dpkg --configure -a

apt-get -o DPkg::Lock::Timeout=120 update
apt-get -o DPkg::Lock::Timeout=120 install -y --no-install-recommends \
    ca-certificates curl git python3

install -d -m 0755 /etc/apt/keyrings
curl --fail --silent --show-error --location --retry 3 \
    https://download.docker.com/linux/ubuntu/gpg \
    --output /etc/apt/keyrings/docker.asc
chmod 0644 /etc/apt/keyrings/docker.asc

cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

apt-get -o DPkg::Lock::Timeout=120 update
apt-get -o DPkg::Lock::Timeout=120 install -y --no-install-recommends \
    docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker.service containerd.service
usermod -aG docker "${docker_user}"

if ! docker network inspect cluster-jam-backend >/dev/null 2>&1; then
    docker network create cluster-jam-backend
fi

docker version
docker compose version
docker buildx version

printf '\nDocker preparado. Abre una sesion nueva con vagrant ssh.\n'

