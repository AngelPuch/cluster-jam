# Registration messaging verification

Run date: 29 October 2026, America/Mexico_City.
Branch: `feat/profile/add-rabbitmq-consumer`.
Base: `d3c788d0091bff24dc8ee6d7adbda0f76ed3adc7`, after the authorized squash
merge of PR #47. The pre-existing Auth lockfile modification is preserved and
excluded from this branch.

This PR adds the real RabbitMQ-to-PostgreSQL provisioning path; it does not
complete JWT/onboarding HTTP, addresses, Orders authorization or deployment.

## Implementation and compatibility

The listener uses the same `amqplib` 0.10.9 and types 0.10.8 as Auth, together
with class-transformer 0.5.1, class-validator 0.15.1 and the same OpenTelemetry
versions. Existing locked dependency versions did not change.

`profile-topology.json` supplies the shared broker resource/permission contract
to both the consumer and deployment preparation. The main classic queue keeps
its name and arguments. Two private direct exchanges, two quorum TTL retry
queues and a quorum DLQ are added. No queue deletion, event change, new Auth
runtime dependency or cross-service database access is introduced.

The consumer validates the complete versioned payload, matching aggregate/user,
versions, timestamp, unknown fields, email and supplied AMQP metadata. It
deduplicates through the existing transactional provisioner. ACK follows commit,
or a confirmed mandatory persistent handoff. Uncertain handoffs close the
connection without ACK so redelivery remains safe. The three scheduled attempts
include the first; retry waits are 5 and 30 seconds outside tests. Transport
redelivery may repeat an unconfirmed attempt and does not add a configured
fourth retry. Permanent failures and unsupported contracts go to DLQ.

Profile can read the identity exchange and declare/bind its own resources, but
cannot publish to or configure `identity.events`. TLS certificate verification
is always enabled and staging/production reject plaintext AMQP. Reconnection,
consumer-aware readiness, shutdown draining, JSON log allowlists and W3C
consumer spans are implemented.

## Executed checks

| Check | Result |
| --- | --- |
| `npm run build` | Pass; topology JSON included in compiled output |
| `npm run typecheck` | Pass for source and tests |
| `npm run lint` | Pass, zero allowed warnings |
| `npm run format:check` | Pass |
| `npm test -- --runInBand` | 7 suites, 77 tests pass |
| `npm run test:e2e -- --runInBand` | 1 suite, 5 tests pass |
| `npm run test:integration` | 2 suites, 23 tests pass against real RabbitMQ/PostgreSQL |
| `python -m unittest discover -s infra/profile -p 'test_*.py' -v` | 2 tests pass |
| Test broker Compose startup | Healthy; pinned RabbitMQ 4.3.6 image actually downloaded and started |

Total: **105 Jest tests and 2 infrastructure tests passing**. Jest's configured
ESM execution emits its VM-module warning and a JSON-import deprecation notice;
neither is represented as a failed check or hidden by a warning suppression.

Node 22.20.0, PostgreSQL 18.6 and RabbitMQ 4.3.6 were used. PostgreSQL ran in the
same isolated temporary instance as the persistence verification. The broker
ran only in Compose project `cluster-jam-profile-test`, bound to loopback ports
5679 and 15679. Each messaging test created and removed a unique vhost and
scoped users; the suite also created and removed only its own PostgreSQL DB.
Existing application databases, containers and broker vhosts were not used.

## Critical-flow evidence

`test/registration-messaging.integration-spec.ts` executes these real cases:

1. Auth's actual event factory and RabbitMQ publisher publish a compatible
   event; Profile creates exactly one PENDING profile and inbox row. Publishing
   the same event again is consumed successfully without a duplicate profile.
2. A real PostgreSQL table lock holds provisioning in flight; RabbitMQ reports
   the message unacknowledged and another DB connection sees no committed inbox
   row. Releasing the lock permits commit and ACK.
3. An unsupported version reaches DLQ with its unchanged body and no DB write.
4. Real PostgreSQL triggers raise two serialization failures; both transactions
   roll back, and the third scheduled processing attempt creates the profile.
5. Persistent transient failures exhaust exactly three attempts, reach DLQ,
   and leave no profile or processed inbox row.
6. A permanent database constraint rejection reaches DLQ on the first attempt.
7. Removing the DLQ binding makes mandatory publication return; the original
   stays queued. Reconnection restores bindings and redelivery reaches DLQ.
8. Removing the retry return route beyond TTL does not lose the message.
   Restoring it delivers the same body from the quorum retry queue.
9. Closing the consumer connection after a real commit causes redelivery; an
   edited COMPLETED profile and its timestamps remain unchanged, with one inbox.
10. The production permission regex permits Profile's declarations/consumption
    and denies publishing to the identity exchange.
11. The actual AppModule boots with real broker and DB dependencies, consumes
    through its injected adapter, returns readiness 200 and closes cleanly.

The existing 12 persistence integration tests still pass. Unit tests additionally
cover malformed/oversized/invalid UTF-8 messages, metadata mismatches, headers,
publisher returns/NACKs/timeouts/connection loss, no ACK before handoff, retry
limits, config validation and log privacy/trace propagation. Health HTTP now
also checks unavailable-consumer readiness without affecting liveness.

The two infrastructure tests verify generated shared definitions, stable secret
hashes, unchanged Auth permissions, canonical queues/bindings and scoped Profile
permissions without writing any real deployment secrets.

## Observed failures and resolution

The first return-route recovery test used a 45-second timeout. The real broker
reported `dead_letter_worker_publisher_confirm_timeout=180000`: recovery was
waiting on that internal timer. The disposable test Compose configuration now
sets that timer to 1000 milliseconds. The corrected real retention/recovery
test passes. Production's timer and resource configuration are unchanged.

The Windows sandbox also blocked local sockets and temporary fixture writes;
those checks passed when rerun with approved access. Initial ESM reflection,
AMQP unknown-property typing and dynamic-import resolution issues were fixed
before the successful type/lint/test checks.

## Remaining acceptance work

This verifies Auth's real event creation/publication code, not a new live
Supabase signup and trigger/outbox drain. That broader acceptance stack remains
for the later integration/CI milestone. AMQPS policy and certificate verification
are implemented; this test broker uses local plaintext AMQP, so a real broker
TLS deployment test is not claimed.

No Profile production image, full Compose deployment, JWT/owner API, Orders
authorization or Swagger result is claimed here. Their implementation follows
the reviewed branch sequence. No new migration was necessary in this PR.
