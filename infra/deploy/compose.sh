#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$task_root"
target="${1:?Usage: compose.sh shared|auth|personalization <compose arguments>}"
shift
case "$target" in shared|auth|personalization) ;; *) exit 2 ;; esac
configuration="infra/$target/.env"
if [[ "$target" == personalization ]]; then
    configuration=infra/personalization/deployment.env
fi
arguments=(--env-file "$configuration")
if [[ -f "infra/$target/release.env" ]]; then
    arguments+=(--env-file "infra/$target/release.env")
fi
# Compose reads ambient variables before --env-file. Keep deployment values
# authoritative, even if this shell was used for local development earlier.
unset AUTH_IMAGE BROKER_REVISION HTTPS_BIND_IP LOG_LEVEL
unset SUPABASE_URL SUPABASE_JWKS_URL
if [[ "$target" == personalization ]]; then
    unset PERSONALIZATION_IMAGE_TAG PERSONALIZATION_GIT_SHA SUPABASE_ISSUER
    unset SUPABASE_STORAGE_BUCKET DOWNLOAD_URL_TTL_SECONDS MIN_PRINT_DPI
    unset IMAGE_MAX_WIDTH_PX IMAGE_MAX_HEIGHT_PX IMAGE_MAX_PIXELS
    unset WORKER_BATCH_SIZE WORKER_POLL_SECONDS
    arguments+=(-f infra/personalization/compose.yaml
        -f infra/personalization/compose.storage.yaml
        -f infra/personalization/compose.deploy.yaml)
else
    arguments+=(-f "infra/$target/compose.yaml")
fi
exec docker compose --project-name "cluster-jam-$target" \
    "${arguments[@]}" "$@"
