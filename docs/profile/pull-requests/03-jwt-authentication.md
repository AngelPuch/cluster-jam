Profile had asynchronous provisioning but no local user-token verification
boundary. Add a jose/JWKS adapter behind an application port, a Bearer guard,
immutable signed identity context and sanitized authentication Problem Details.
Use ES256/RS256, exact issuer/authenticated audience, expiry/nbf and UUID sub,
with cliente/administrador only from protected app_metadata.app_role. Do not
call Auth or Supabase user/session endpoints on each request.

Reuse one bounded JWKS cache with refresh cooldown, shared downloads, timeout
and no redirect following. Reject malformed/forged/anonymous/backend credentials,
unsupported signing algorithms, duplicate Authorization fields and identity
supplied in body/query/headers. Known warm keys work during a temporary outage;
unavailable required keys fail closed. Health remains public; no new business
or probe route is exposed by production.

Validation: build, source/test types, zero-warning lint and formatting pass.
All 183 Jest tests pass: 137 unit, 23 HTTP with a real loopback JWKS server,
and 23 PostgreSQL/RabbitMQ regression tests. Real cryptography, rotation/cache,
timeout/error privacy, protected roles, guard/decorator wiring and AppModule
startup with the existing event consumer are covered. See verification-03.md.

BREAKING CHANGE: set public SUPABASE_URL and its matching SUPABASE_JWKS_URL
before application startup and use an asymmetric Supabase signing key. Issuer
is derived; audience is authenticated. No Supabase API key/shared secret or
database migration is required. Migration tooling remains independent of
identity settings. Auth's runtime/event/lockfile changes are excluded.

Own-profile GET/PATCH and their Swagger/authorization tests follow in the next
reviewed branch after this foundation is squash merged.
