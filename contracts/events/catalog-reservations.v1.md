# Catalog reservations v1

Branch 9 consumes only `cmd.catalog.reserve-stock.v1`.
The input exchange is `catalog.commands`; the durable queue is `catalog.commands.v1`.
Outbox results target `catalog.events` and `orders.checkout.v1`.

| Message | data |
| --- | --- |
| cmd.catalog.reserve-stock.v1 | quoteValidUntil, lines[{variantId, quantity, expectedBasePriceCents}] |
| catalog.inventory.reservation-created.v1 | reservationId, expiresAt |
| catalog.inventory.reservation-rejected.v1 | reason: OUT_OF_STOCK, VARIANT_UNAVAILABLE, PRICE_CHANGED or QUOTE_EXPIRED |

All messages use messageId (UUID), type (the complete routing key), orderId (UUID),
occurredAt (ISO-8601 instant), and data. Publish JSON as persistent with AMQP
message_id=messageId, correlation_id=orderId and type=type.
Do not regenerate an ID when retrying publication.

One order is one purchase. The reserve handler deduplicates by message ID and,
as a business safeguard, by order ID. The inbox consumer name is the operation
type, so future confirmation/release handlers have their own namespace.
An already processed order retains its first reserve result; creating a new
purchase requires a new order. No body hashes are compared.

Quantities are positive integers. Base prices are positive integer MXN cents,
up to the existing administrative limit of 10000000. Variants must be distinct.
Orders groups design lines by variant and supplies its server-side quote.
Timestamps use ordinary ISO-8601; fractional seconds are not fixed.

Example (replace identifiers/times when used by a real producer):

```json
{
  "messageId": "00000000-0000-4000-8000-000000000003",
  "type": "cmd.catalog.reserve-stock.v1",
  "orderId": "00000000-0000-4000-8000-000000000001",
  "occurredAt": "2026-11-25T18:00:00Z",
  "data": {
    "quoteValidUntil": "2026-11-25T18:05:00Z",
    "lines": [{
      "variantId": "00000000-0000-4000-8000-000000000004",
      "quantity": 2,
      "expectedBasePriceCents": 19900
    }]
  }
}
```

Inbox, the whole basket or rejection, and its outbox result commit together.
The consumer then acknowledges the delivery. Invalid input and three exhausted
technical attempts are rejected without requeue into the native DLQ.
Branch 9 stores results as PENDING; branch 11 publishes them.
Branch 10 supplies confirmation, release, expiry and physical stock consumption.
