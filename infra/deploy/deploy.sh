#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$task_root"
target="${1:-all}"
case "$target" in auth|shared|all|build|personalization) ;; *) exit 2 ;; esac
if [[ "$target" == personalization ]]; then
    exec bash infra/deploy/deploy-personalization.sh
fi
if [[ -n "$(git status --porcelain)" ]]; then
    printf 'Commit or preserve source changes before deployment.\n' >&2
    exit 1
fi
[[ -f infra/shared/.env && -f infra/auth/.env ]]
[[ -f infra/shared/.pki/ca.crt ]]
if [[ -f infra/shared/.pki/recreate-required && "$target" != all && "$target" != build ]]; then
    printf 'Certificate renewal requires deploy.sh all.\n' >&2
    exit 1
fi
compose() { bash infra/deploy/compose.sh "$@"; }
write_release() {
    local destination="$1"
    if [[ -f "$destination" ]] && ! cmp -s "$destination.new" "$destination"; then
        cp "$destination" "$destination.previous"
    fi
    mv "$destination.new" "$destination"
}
umask 077
if [[ "$target" == auth || "$target" == all || "$target" == build ]]; then
    revision="$(git rev-parse HEAD)"
    auth_version="$(python3 -c 'import json; print(json.load(open("services/authService/package.json"))["version"])')"
    auth_image="cluster-jam/auth:${auth_version}-${revision}"
    if ! docker image inspect "$auth_image" >/dev/null 2>&1; then
        docker build -f services/authService/Dockerfile \
            --build-arg "SERVICE_VERSION=$auth_version" \
            --build-arg "VCS_REF=$revision" -t "$auth_image" .
    fi
    printf 'AUTH_IMAGE=%s\n' "$auth_image" > infra/auth/release.env.new
    write_release infra/auth/release.env
    compose auth config --quiet
fi
if [[ "$target" == shared || "$target" == all || "$target" == build ]]; then
    broker_revision="$(cat infra/shared/rabbitmq.conf \
        infra/shared/.pki/rabbitmq.crt infra/shared/.pki/rabbitmq.key \
        infra/shared/.pki/ca.crt infra/shared/.secrets/rabbitmq_definitions.json \
        | sha256sum | cut -d' ' -f1)"
    printf 'BROKER_REVISION=%s\n' "$broker_revision" > infra/shared/release.env.new
    write_release infra/shared/release.env
    compose shared config --quiet
fi
if [[ "$target" == build ]]; then
    printf 'Auth image built; Compose models validated. No containers started.\n'
    exit 0
fi
if ! docker network inspect cluster-jam-backend >/dev/null 2>&1; then
    docker network create cluster-jam-backend
fi
recreate=()
if [[ -f infra/shared/.pki/recreate-required ]]; then recreate=(--force-recreate); fi
if [[ "$target" == shared || "$target" == all ]]; then
    compose shared up -d --no-build "${recreate[@]}" --wait --wait-timeout 180 rabbitmq
fi
if [[ "$target" == auth || "$target" == all ]]; then
    compose auth up -d --no-build --pull never --force-recreate \
        --wait --wait-timeout 180 auth
    compose auth exec -T auth node < infra/deploy/check-auth.cjs
    compose auth exec -T auth node -e \
        "fetch('http://127.0.0.1:8080/health/ready',{signal:AbortSignal.timeout(10000)}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
fi
if [[ "$target" == shared || "$target" == all ]]; then
    compose shared up -d --no-build --force-recreate --wait --wait-timeout 90 nginx
    compose shared exec -T nginx nginx -t
    compose shared ps
fi
if [[ "$target" == auth || "$target" == all ]]; then compose auth ps; fi
if [[ "$target" == all ]]; then rm -f infra/shared/.pki/recreate-required; fi
printf 'Deployment finished. Verify HTTPS with the trusted staging CA.\n'
