#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$task_root"
if [[ -n "$(git status --porcelain)" ]]; then
    printf 'Commit or preserve source changes before deployment.\n' >&2
    exit 1
fi
[[ -f infra/personalization/deployment.env && -f infra/shared/.env ]]
[[ -f infra/shared/.pki/personalization-grpc.crt ]]
[[ -f infra/shared/.pki/personalization-grpc.key ]]
[[ -f infra/shared/.pki/ca.crt ]]
if [[ -f infra/shared/.pki/recreate-required ]]; then
    printf 'Finish shared certificate renewal with deploy.sh all first.\n' >&2
    exit 1
fi
compose() { bash infra/deploy/compose.sh "$@"; }
umask 077
revision="$(git rev-parse HEAD)"
service_version="$(python3 -c 'import tomllib; print(tomllib.load(open("services/personalizationService/pyproject.toml", "rb"))["project"]["version"])')"
image_tag="$service_version-$revision"
image="cluster-jam/personalization:$image_tag"
if ! docker image inspect "$image" >/dev/null 2>&1; then
    docker build --target runtime --build-arg "VCS_REF=$revision" \
        -t "$image" services/personalizationService
fi
destination=infra/personalization/release.env
printf 'PERSONALIZATION_IMAGE_TAG=%s\nPERSONALIZATION_GIT_SHA=%s\n' \
    "$image_tag" "$revision" > "$destination.new"
if [[ -f "$destination" ]] && ! cmp -s "$destination.new" "$destination"; then
    cp "$destination" "$destination.previous"
fi
mv "$destination.new" "$destination"
compose personalization --profile images --profile rpc config --quiet
if ! docker network inspect cluster-jam-backend >/dev/null 2>&1; then
    docker network create cluster-jam-backend
fi
# This provisioner preserves existing passwords and never applies schema DDL.
python3 infra/personalization/provision_local.py
compose personalization up -d --no-build --wait --wait-timeout 120 db-personalizacion
# This explicit, one-shot step must succeed before starting the new release.
compose personalization run --rm --no-deps --pull never personalization-migrate
compose personalization run --rm --no-deps --pull never personalization-storage check
compose personalization --profile images --profile rpc up -d --no-build \
    --pull never --force-recreate --wait --wait-timeout 120 \
    personalization personalization-worker personalization-grpc
compose personalization exec -T personalization python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=10).close()"
compose personalization exec -T personalization-grpc python -m personalization.interfaces.grpc.health
# Recreate only the gateway; Auth and RabbitMQ containers keep their state.
compose shared up -d --no-deps --no-build --force-recreate --wait --wait-timeout 90 nginx
compose shared exec -T nginx nginx -t
compose shared exec -T nginx curl --fail --silent --show-error \
    --max-time 10 --cacert /run/config/cluster-ca.crt \
    --resolve clusterjam.test:8443:127.0.0.1 \
    https://clusterjam.test:8443/health/personalization/ready > /dev/null
compose personalization --profile images --profile rpc ps
printf 'Personalization deployed. Verify HTTPS with the trusted staging CA.\n'
