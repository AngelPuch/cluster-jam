#!/bin/sh
set -eu
install -d -m 0700 -o postgres -g postgres /run/postgresql/profile-tls
install -m 0600 -o postgres -g postgres /run/secrets/profile_db_tls_key /run/postgresql/profile-tls/server.key
exec /usr/local/bin/docker-entrypoint.sh "$@"
