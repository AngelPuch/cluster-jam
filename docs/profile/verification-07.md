# Profile CI and real registration acceptance

Run date: 30 October 2026, America/Mexico_City.
Branch: `ci/profile/add-automated-checks`.
Base: `781ed59c989c32cfa8341eb1cc899fa24907a527`.

PR #52 was squash merged after explicit authorization and successful remote
Python/Docker checks. Main was updated before this branch. The user requested
fewer routine tests for this school project; no new broad regression suite or
repeat of the previous 328 Jest cases/image battery was performed here.

## Single real acceptance scenario

```sh
python infra/profile/verify_registration.py
```

Passed locally with the locked Supabase CLI 2.118.0, real Supabase PostgreSQL/
Auth/gateway/mail containers, separate Profile PostgreSQL and RabbitMQ. The
helper builds both applications once and uses their actual compiled AppModules.
There are no provider overrides, fabricated events or direct profile inserts.

The actual Auth `POST /api/v1/registrations` returned 201 with pending email
confirmation and a new identity. Supabase's versioned trigger wrote its outbox;
Auth's running worker used a login with the existing restricted
`auth_outbox_publisher` membership, confirmed publication through RabbitMQ and
marked the outbox row published. Profile's real listener persisted the event
through its transactional repository. The acceptance asserts:

- Exactly one profile associated with the registered identity.
- Initial registration contact email, null name/phone and PENDING onboarding.
- One inbox record with the actual outbox event ID and zero initial addresses.
- Protected `app_metadata.app_role=cliente` on the real Supabase identity.

The observed result was:

```text
PASS: real Auth signup -> Supabase trigger/outbox -> RabbitMQ -> minimum Profile (one acceptance scenario).
```

Cleanup removed the uniquely named Supabase/Compose resources and temporary
fixture directory. Existing databases/volumes were not reset. Occupied fixture
ports cause an abort before startup. Provider keys are captured privately and
passed only through the child environment. A Windows CLI-output decoding issue
was corrected by explicitly reading UTF-8 with replacement; it did not prevent
the scenario or cleanup from passing.

This scenario ends at provisioning. It does not perform email confirmation or
login and does not claim that local Supabase's signing defaults exercise
Profile's asymmetric JWT boundary. Real signed JWT/owner HTTP and TLS behavior
were already verified in milestones 03–06.

## Lean workflow and checks

`.github/workflows/profile-ci.yml` runs on scoped PR/main changes and manual
dispatch. It installs locked dependencies, checks types/ESLint/formatting,
verifies this one signup, then checks generated OpenAPI without a second build.
Actions and infrastructure images are pinned. Full image build/TLS verification
is available only when a manual dispatch selects `extended_checks=true`.

The following local checks passed for this branch:

| Check | Result |
| --- | --- |
| Auth and Profile production build | Passed during the acceptance helper |
| Profile `npm run typecheck` | Passed |
| Profile `npm run lint` and `npm run format:check` | Passed, zero warnings |
| Offline compiled OpenAPI check | Current committed contract |
| Infrastructure Ruff check/format and acceptance CJS Prettier | Passed |

The earlier full regression/image evidence remains in `verification-06.md`;
those commands were not rerun here. The existing unrelated Auth lockfile
modification remains excluded. The final PR requires remote CI and explicit
authorization to squash merge. No staging/production rollout was performed.
