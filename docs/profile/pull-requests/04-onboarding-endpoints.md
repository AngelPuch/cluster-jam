Customers could be provisioned and authenticated but could not read or complete
their own profile. Add GET/PATCH `/api/v1/profiles/me` with identity taken only
from verified JWT sub, a storage port/use cases, dedicated HTTP DTOs and a real
TypeORM repository. Reads/updates never create missing profiles; return
404 PROFILE_NOT_READY until registration processing arrives.

Validate partial fullName/phone/contactEmail updates, preserve omitted fields,
reject null/blank/privileged fields and derive PENDING/COMPLETED without requiring
an address. Keep contact email independent from login credentials and repeated
registration. Historical null-email records require explicit legitimate repair.
Document the additional phone-format recommendation and existing SQL limits.

Use strong ETag/If-Match and a PostgreSQL row lock to prevent lost writes.
Missing preconditions return 428, unsupported syntax 400 and stale revisions
412. Add sanitized RFC 9457 handling, strict validation, Helmet, HTTP/W3C trace
correlation and private-field exclusion. Health remains public/unversioned.

Expose `/docs/` and `/openapi.json`, version the implemented API contract and
provide offline export/drift checks using actual AppModule metadata in Nest
preview mode, without infrastructure connections or persistence substitutes.

Validation: build, source/test types, zero-warning ESLint, formatting and diff
checks pass. All 242 Jest tests pass: 171 unit, 23 JWT/health HTTP and 48 real
PostgreSQL/RabbitMQ integration cases (25 owner HTTP). The live OpenAPI exactly
matches the committed contract; a deliberate drift probe fails and restoration
passes. Tests cover owner isolation, rollback, legacy repair, actual database
failure, signed-token authentication, simultaneous writes and messaging
regression. See `docs/profile/verification-04.md` for commands and limits.

No new migration or environment requirement. Swagger/Helmet match Auth's
existing versions. Auth changes are excluded. Addresses, Orders service
identity/contact, deployment and CI follow in separate reviewed branches.
