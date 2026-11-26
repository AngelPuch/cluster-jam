# Catalog reservations v1 (branches 9-11)

All commands target the topic exchange catalog.commands and durable queue
catalog.commands.v1. Results target catalog.events and orders.checkout.v1.
Results enter outbox as PENDING. With the branch-11 publisher enabled, they
become PUBLISHED after a positive publisher confirm without a mandatory return.

| Type / routing key | data |
| --- | --- |
| cmd.catalog.reserve-stock.v1 | quoteValidUntil, lines[{variantId, quantity, expectedBasePriceCents}] |
| cmd.catalog.confirm-reservation.v1 | reservationId, paymentId |
| cmd.catalog.release-reservation.v1 | reservationId, reason |
| cmd.catalog.consume-stock.v1 | reservationId |
| catalog.inventory.reservation-created.v1 | reservationId, expiresAt |
| catalog.inventory.reservation-rejected.v1 | reason: OUT_OF_STOCK, VARIANT_UNAVAILABLE, PRICE_CHANGED or QUOTE_EXPIRED |
| catalog.inventory.reservation-confirmed.v1 | reservationId, paymentId |
| catalog.inventory.reservation-released.v1 | reservationId, reason |
| catalog.inventory.reservation-expired.v1 | reservationId, expiresAt |
| catalog.inventory.stock-consumed.v1 | reservationId |

The common envelope is messageId (UUID), type (full routing key), orderId (UUID),
occurredAt (normal ISO-8601 instant) and data.
Publish persistent JSON, with AMQP message_id=messageId, correlation_id=orderId
and type=type. Preserve IDs on retry. No JSON canonicalization or body hashes.

Quantities and base prices are positive integer values. Base prices use MXN
cents up to the existing 10000000 administrative limit. Variants are distinct.
The release reason is required and at most 200 characters.
Each reservation ID must belong to the envelope orderId.

One order is one purchase. Inbox identifies its logical consumer by operation
type and deduplicates messages and operations for that order. Future purchases
must use a new order. Exact repeated deliveries do not create new output facts.

| Transition | Inventory effect |
| --- | --- |
| New ACTIVA | Increase reserved only |
| ACTIVA -> CONFIRMADA | No inventory delta; remember paymentId |
| ACTIVA/CONFIRMADA -> LIBERADA | Decrease reserved once |
| ACTIVA -> EXPIRADA | Decrease reserved once |
| CONFIRMADA -> CONSUMIDA | Decrease physical and reserved once |

Confirmation rechecks the PostgreSQL wall clock after obtaining the reservation
lock. It succeeds only strictly before expiry. A late confirmation expires an
active reservation immediately, including releasing stock and writing the
expiration event in the same transaction.
The periodic worker checks due active reservations every 30 seconds.

Confirmation of an expired/released reservation and release of an already
expired/released reservation keep the existing terminal evidence. They do not
create another confirmed/released event. The inbox result points to that
existing event. Confirmed reservations do not expire.

Unknown or foreign reservation IDs, conflicting payment identities and invalid
state transitions roll back and are rejected without requeue to DLQ. They do
not create preventive rows or false release events. Technical failures retain
the three-attempt policy. ACK follows commit.

Orders sends confirmation only after it has accredited payment, and serializes
production against cancellation on its order row. Catalog does not contact
Stripe or decide reimbursement. Production consumption is after checkout and
does not change its pivot. No AMQP status-query protocol is introduced.

## Delivery and publication

The message contracts above do not change in branch 11.
The publisher polls pending rows every five seconds, at most ten per pass,
with a separate SQL transaction per row. It holds a NO KEY UPDATE row lock
through publication and SQL commit, preserving key-share reads of existing FKs.
The deployment assumes one instance and one scheduled publisher.

Correlated confirms, returns and mandatory publication are enabled together.
Messages use persistent delivery mode. A positive confirm alone does not prove
a route: the publisher also checks the returned-message result.
A publication failure retains PENDING and the same messageId for a later cycle.
If the broker accepted a message before its SQL mark was lost, delivery may
repeat. Inbox remains responsible for an idempotent consumer effect.

PUBLISHED describes broker acceptance/routing, not Orders' business result.
No AMQP status queries, new business messages or HTTP reservation routes are
introduced. Native DLQ remains for rejected consumer deliveries; publication
failures are retried from outbox.
