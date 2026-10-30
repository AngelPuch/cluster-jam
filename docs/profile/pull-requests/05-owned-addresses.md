Authenticated customers could update their profile but had no address API.
Add owned address list/read/create/update/delete under
`/api/v1/profiles/me/addresses`, with JWT-sub ownership, dedicated DTOs,
application use cases/storage port and a real TypeORM address-book repository.
Include individual GET so clients can follow creation Location and retrieve
the item ETag for editing/deletion. Foreign/missing addresses are hidden with
the same 404 even for administrator identities.

Serialize address-book writes with a parent-profile row lock and validate
ETag/If-Match inside the transaction. Create uses the collection tag; edit/delete
use the target item tag, which also covers the book. Concurrent default choices
cannot overwrite a stale snapshot. Explicitly selecting a default demotes the
old one atomically; deletion/unsetting can leave none. Keep the existing partial
unique index and local foreign key, with no migration/dependency change.

Validate schema lengths, allowed fields and explicit interior-number clearing;
document uppercase ISO country validation and string postal limits. Preserve
onboarding/contact independence, including legacy null-email owners. Require
JSON before DTO validation, extend sanitized Problem Details and version the
actual Swagger routes, conditional headers, DTOs and error examples.

Validation: 313 Jest cases pass (213 unit, 23 JWT/health HTTP, 77 PostgreSQL/
RabbitMQ integration, including 29 new address cases). Build, source/test types,
zero-warning ESLint, formatting, OpenAPI and diff checks pass. Real database
tests cover owner/admin isolation, conditional concurrent creates/selections,
unique-index enforcement and rollback after a database failure following
default demotion. The served OpenAPI equals the committed contract. See
`docs/profile/verification-05.md` for the matrix, commands and limitations.

Auth changes are excluded. Orders service authentication/contact, Profile
deployment and CI follow in separate reviewed branches.
