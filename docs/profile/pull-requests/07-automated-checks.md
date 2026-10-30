Profile lacked dedicated CI and a complete signup check through Supabase's
actual trigger/outbox. Add a scoped workflow with source quality, one real
registration acceptance scenario and offline OpenAPI drift. Respect the user's
request for fewer routine tests: the full image/TLS stack remains an optional
manual dispatch instead of repeating the earlier regression battery.

The acceptance helper copies Auth's actual local Supabase configuration,
migrations and email templates into a uniquely named disposable project. It
builds both services once, calls Auth's real registration API, runs its restricted
outbox publisher and asserts Profile's real inbox/minimum-profile persistence.
It uses separate databases, loopback dependencies and safe cleanup; provider keys
are captured privately. Add final delivery/verification records and update the
service/deployment instructions. Orders remains explicitly deferred.

Validation: the real signup flow, both builds, Profile types/lint/format,
infrastructure Ruff, acceptance CJS formatting and offline OpenAPI check passed.
The prior 328 Jest cases and complete TLS/image verification are recorded in
milestone 06 and were not rerun for this PR. No production rollout, dependency
upgrade, domain migration or Auth business change. The unrelated existing Auth
lockfile modification remains excluded. See `docs/profile/verification-07.md`
and `docs/profile/final-report.md` for evidence and delivery details.
