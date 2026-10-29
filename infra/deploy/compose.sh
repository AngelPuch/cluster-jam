#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$task_root"
target="${1:?Usage: compose.sh shared|auth <compose arguments>}"
shift
case "$target" in shared|auth) ;; *) exit 2 ;; esac
arguments=(--env-file "infra/$target/.env")
if [[ -f "infra/$target/release.env" ]]; then
    arguments+=(--env-file "infra/$target/release.env")
fi
# Compose reads ambient variables before --env-file. Keep deployment values
# authoritative, even if this shell was used for local development earlier.
unset AUTH_IMAGE BROKER_REVISION HTTPS_BIND_IP LOG_LEVEL
unset SUPABASE_URL SUPABASE_JWKS_URL
exec docker compose --project-name "cluster-jam-$target" \
    "${arguments[@]}" -f "infra/$target/compose.yaml" "$@"
