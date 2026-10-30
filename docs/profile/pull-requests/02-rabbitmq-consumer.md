Profile could provision a transactional minimum profile but did not consume
Auth's registration events. Add a real amqplib consumer that validates the
versioned event, waits for the inbox/profile commit and ACKs successful or
duplicate deliveries. Preserve Auth's event and existing main queue.

Add two progressive quorum TTL retries and a durable DLQ. There are three
scheduled attempts total. Invalid/permanent messages go to DLQ; retry/DLQ
handoffs require persistent mandatory publication and publisher confirms.
Uncertain transfers close without ACK and recover by redelivery. Quorum
at-least-once dead lettering also protects the TTL return leg.

Use one canonical topology/permission definition in the listener and broker
provisioning. Profile has no identity-exchange write permission. Include verified
TLS configuration, reconnection backoff, consumer readiness, shutdown draining
and allowlisted JSON/OpenTelemetry logging without payloads or contact data.

Validation: build, source/test types, lint and formatting pass. All 105 Jest
tests and 2 infrastructure tests pass, including 23 real RabbitMQ/PostgreSQL
integration cases. They execute Auth's actual factory/publisher, transaction
blocking/rollback, bounded retries, unrouted handoff recovery, missing TTL return
route, commit-before-ACK connection loss, permissions and actual AppModule
startup/shutdown. The isolated test broker Compose was run successfully.

No Auth event or runtime code changes, new database migration or production
deployment was required. The unrelated local Auth lockfile edit is excluded.
Live Supabase signup/outbox acceptance, real TLS stack verification, JWT/owner
HTTP, Orders, Swagger and the full Profile image/CI remain subsequent milestones.
