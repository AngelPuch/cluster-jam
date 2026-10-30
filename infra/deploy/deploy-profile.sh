#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$task_root"
if [[ -n "$(git status --porcelain -- services/profileService infra/profile infra/shared infra/deploy contracts/openapi/profile .gitattributes)" ]]; then
    printf 'Commit or preserve Profile deployment source changes before deployment.\n' >&2
    exit 1
fi
[[ -f infra/profile/.env && -f infra/shared/.env && -f infra/shared/.pki/ca.crt ]]
[[ -f infra/profile/.secrets/profile_rabbitmq_uri ]]
if [[ -f infra/shared/.pki/recreate-required ]]; then
    printf 'Finish shared certificate renewal before deploying Profile.\n' >&2
    exit 1
fi
revision="$(git rev-parse HEAD)"
version="$(python3 -c 'import json; print(json.load(open("services/profileService/package.json"))["version"])')"
image="cluster-jam/profile:${version}-${revision}"
if ! docker image inspect "$image" >/dev/null 2>&1; then
    docker build -f services/profileService/Dockerfile \
        --build-arg "SERVICE_VERSION=$version" --build-arg "VCS_REF=$revision" -t "$image" .
fi
umask 077
printf 'PROFILE_IMAGE=%s\n' "$image" > infra/profile/release.env.new
if [[ -f infra/profile/release.env ]] && ! cmp -s infra/profile/release.env.new infra/profile/release.env; then
    cp infra/profile/release.env infra/profile/release.env.previous
fi
mv infra/profile/release.env.new infra/profile/release.env
compose() { bash infra/deploy/compose.sh profile "$@"; }
compose config --quiet
# Shared broker/network are provisioned independently; never recreate another service here.
docker network inspect cluster-jam-backend >/dev/null
compose up -d --no-build --pull never --wait --wait-timeout 180 db-profile
compose run --rm --no-deps profile-migrate
compose up -d --no-deps --no-build --pull never --force-recreate --wait --wait-timeout 180 profile
compose exec -T profile node -e \
    "fetch('http://127.0.0.1:8080/health/ready',{signal:AbortSignal.timeout(10000)}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
compose ps
bash infra/deploy/compose.sh shared up -d --no-deps --no-build --force-recreate --wait --wait-timeout 90 nginx
bash infra/deploy/compose.sh shared exec -T nginx nginx -t
bash infra/deploy/compose.sh shared exec -T nginx curl --fail --silent --show-error \
    --max-time 10 --cacert /run/config/cluster-ca.crt --resolve clusterjam.test:8443:127.0.0.1 \
    https://clusterjam.test:8443/health/profile/ready > /dev/null
printf 'Profile deployment and HTTPS readiness verified.\n'
