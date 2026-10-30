# Local JWT authentication verification

Run date: 29 October 2026, America/Mexico_City.
Branch: `feat/profile/add-jwt-authentication`.
Base: `0a07e76c0aa5a6d2b0c5f3f26a4c9a4924d55a50`.

PR #48 was squash merged only after the user authorized it and both remote
checks completed successfully: Python quality/package and Docker
packaging/database isolation. This JWT branch was then created from updated
main. The pre-existing local Auth lockfile modification remains excluded.

## Delivered security boundary

The application port and immutable identity contain no jose/Nest/provider
details. The infrastructure adapter uses Auth's pinned `jose` 6.2.12 to verify
Supabase ES256/RS256 JWTs locally, matching Personalization's protected role and
user-token rules. The guard obtains identity only from a single Bearer header.
The CurrentIdentity decorator fails closed without a verified guard context.
No profile/address/internal business route or test probe is added to production.

The verifier requires signed sub/exp/iss/aud, UUID subject, the exact configured
issuer, authenticated audience, role=authenticated, non-anonymous identity and
cliente/administrador from app_metadata.app_role. It rejects HS256, unsigned,
expired, not-yet-valid, altered and wrongly signed tokens. user_metadata and
caller-supplied IDs cannot override identity. Public key URLs supplied in JWT
headers are not used.

JWKS lifetime is 600 seconds, missing-key refresh cooldown 30 seconds, and
fetch timeout 5 seconds. Concurrent requests share one download. Keys are
retrieved from the validated project URL without redirect following. An outage
can use still-fresh cached keys; expired caches fail closed. Provider/JSON/key
errors become a safe 503, while invalid credentials are 401 and invalid
protected roles are 403. Responses are RFC 9457 Problem Details with no-store,
traceId and no query, token or raw provider detail.

## Required configuration migration

Application startup now requires `SUPABASE_URL` and `SUPABASE_JWKS_URL`.
Copy the public project URLs from `.env.example`, replace the placeholder,
and configure an asymmetric signing key in Supabase before starting Profile.
The optional issuer must match the derived /auth/v1 issuer; the audience is
fixed to authenticated. HTTPS is required except loopback development/test.
No privileged Supabase key or shared JWT secret is introduced. Database
migration commands still validate only database configuration.

This is an application configuration compatibility change, marked with `!` in
the Conventional Commit/PR title. Existing tokens, Auth behavior and database
schema were not changed; no new migration is needed.

## Executed checks

| Command | Observed result |
| --- | --- |
| `npm run build` | Pass |
| `npm run typecheck` | Pass, source and test configurations |
| `npm run lint` | Pass with zero allowed warnings |
| `npm run format:check` | Pass |
| `npm test -- --runInBand` | 9 suites, 137 tests pass |
| `npm run test:e2e -- --runInBand` | 2 suites, 23 tests pass |
| `npm run test:integration` | 2 suites, 23 tests pass with real PostgreSQL/RabbitMQ |

Total: **183 passing Jest tests**. The unchanged infrastructure Python tests
were not rerun for this branch; their prior result remains in verification-02.
Existing Jest ESM and JSON-import deprecation notices remain visible; none is
hidden by a new warning suppression.

## Requirement to verification matrix

| Requirement | Evidence |
| --- | --- |
| Local signatures | Real ES256 and RS256 keys/signatures pass in unit and HTTP suites |
| Required claims and expiry | Missing/invalid sub, exp, iss, aud; future nbf; anonymous and backend roles are rejected |
| Forgery resistance | Modified payload, other private key, untrusted key URL and unsupported algorithms fail |
| Protected roles | Both documented roles accepted; missing/invalid app_metadata rejected; user_metadata cannot elevate |
| Identity ownership source | HTTP body/query/x-user-id attempts still return the signed sub and protected role |
| Bearer boundary | Missing, malformed, duplicate raw Authorization headers, cookie/query-only credentials rejected |
| Key cache | Concurrent validation performs one download; known keys survive temporary outage while fresh |
| Rotation/revocation window | Unknown kid refreshes after cooldown; retired keys disappear after cache lifetime |
| Safe dependency failure | Cold outage, malformed/empty/ambiguous JWKS and redirects fail closed without provider detail |
| Bounded network wait | A real unresponsive JWKS server returns controlled 503 after the five-second timeout |
| HTTP error contract | 401/403/503 Problem Details, no-store, Bearer challenge on 401, sanitized instance and traceId |
| No per-request session lookup | The real JWKS server records only its key-set route, with one call while the cache is warm |
| Existing service behavior | All persistence/messaging tests pass; actual AppModule consumes events and shuts down with SecurityModule installed |

Unit tests exercise real cryptography with controlled JWKS transport. HTTP
tests use a real loopback Node JWKS server and real Nest guard/module/filter;
only the test file declares probe controllers. Ephemeral private signing keys
are generated in memory and are never committed. The raw HTTP duplicate-header
test includes Host so it reaches authentication rather than failing HTTP syntax.

The existing disposable PostgreSQL and isolated RabbitMQ test project were
used for regression. Only test-created databases, vhosts and users were cleaned
by the suites. No production account, database, broker vhost or signing key
was modified.

## Scope and remaining verification

These JWTs are signed test fixtures with Supabase-compatible claims, not tokens
issued by a live Supabase signup. Full signup/outbox acceptance, production TLS
stack/image checks, own profile/address routes, checkout service authorization,
Swagger and Profile CI remain in their planned milestones. The guard is ready
for the onboarding-controller PR; complete resource authorization is not claimed
before those controllers/repositories exist.
