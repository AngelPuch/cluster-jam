# Payments purchase messages v1

Payments participates in the Orders-orchestrated purchase saga. Commands use
`payments.commands` and queue `payments.commands.v1`; results use
`payments.events` and are bound to `orders.checkout.v1`. Payment preparation
and its transactional inbox/outbox, AMQP enable-command consumption and outbox
publication, signed payment/refund webhooks and cancel/full-refund handlers are implemented.
Pending refunds keep the payment credited until total provider success is confirmed.

The envelope matches Catalog: `messageId` (UUID), `type` (full routing key),
`orderId` (UUID), `occurredAt` (ISO-8601 instant) and `data`.
AMQP `message_id` equals `messageId`, `correlation_id` equals `orderId` and
`type` equals the routing key. Use persistent JSON, durable queues,
mandatory publication and publisher confirms. Preserve IDs on retry.

| Type / routing key                  | data                                                                          |
| ----------------------------------- | ----------------------------------------------------------------------------- |
| `cmd.payments.enable-payment.v1`    | `reservationId`, `reservationExpiresAt`, `buyerId`, `amountCents`, `currency` |
| `cmd.payments.cancel-payment.v1`    | `paymentId`, `reason`                                                         |
| `cmd.payments.refund-full.v1`       | `paymentId`, `reason`                                                         |
| `payments.payment.enabled.v1`       | `paymentId`, `reservationId`                                                  |
| `payments.payment.succeeded.v1`     | `paymentId`, `reservationId`, `amountCents`, `currency`                       |
| `payments.payment.not-completed.v1` | `paymentId`, `status` (`CANCELADO` or `FALLIDO`), `reason`                    |
| `payments.refund.succeeded.v1`      | `paymentId`, `amountCents`, `currency`                                        |

Amounts are positive safe integers in MXN cents. Orders supplies the accepted
price and authenticated buyer; Android does not choose the amount. Action
reasons are nonblank strings of at most 200 characters. Identifiers must belong
to the envelope order. A new purchase uses a new order; one logical payment
and at most one full refund exist for that order/payment.

Only confirmed provider evidence produces payment/refund success. A temporary
failure or reusable declined card is not a terminal `FALLIDO`. A pending refund
does not produce refund success. Late preparation must not demote a paid or
refunded payment. Expiry does not prove that a previous Stripe call had no effect.

Create/cancel/refund use stable Stripe keys `payment:create:<orderId>`,
`payment:cancel:<paymentId>` and `payment:refund:<paymentId>`. Persist local
operation identity before the provider call, call outside the business SQL
transaction, then persist the result, completed inbox and outbox together.
Recover uncertain provider results using the original references/operation.

Inbox deduplicates by consumer and message ID; no body hashes or canonical JSON.
The financial state and outgoing event commit before ACK. An outbox worker
publishes every five seconds with one execution at a time. Invalid/exhausted
consumer deliveries use the native DLQ after at most three brief technical
attempts; publication failures remain pending in outbox.

Client secrets, card data, tokens and credentials never appear in AMQP or logs.
The client obtains payment access only through authenticated owner-scoped HTTP.
Orders owns saga state, the reservation-confirmation pivot and compensation.
