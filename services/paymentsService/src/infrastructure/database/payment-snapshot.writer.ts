import { randomUUID } from 'node:crypto';
import type { EntityManager } from 'typeorm';
import type { StripePaymentSnapshot } from '../../application/ports/payment-notice.port';
import { PaymentProviderMismatch } from '../../application/payments/payment.error';
import { PaymentMessageType } from '../../application/payments/payment-messages';
import { PaymentStatus } from '../../application/payments/payment';
import { PaymentEntity } from './entities/payment.entity';
import { OutboxEntity } from './entities/outbox.entity';

// Call with the payment row locked inside the caller's inbox transaction.
export async function persistPaymentSnapshot(
    manager: EntityManager,
    payment: PaymentEntity,
    intent: StripePaymentSnapshot,
): Promise<void> {
    if (
        payment.id !== intent.paymentId ||
        payment.orderId !== intent.orderId ||
        payment.buyerId !== intent.buyerId ||
        payment.reservationId !== intent.reservationId ||
        payment.amountCents !== intent.amountCents ||
        payment.currency !== intent.currency ||
        (payment.stripePaymentIntentId && payment.stripePaymentIntentId !== intent.id) ||
        (!payment.stripePaymentIntentId && !payment.stripeCreationStartedAt)
    )
        throw new PaymentProviderMismatch();
    const firstReference = !payment.stripePaymentIntentId;
    payment.stripePaymentIntentId = intent.id;
    if (![PaymentStatus.Paid, PaymentStatus.Refunded].includes(payment.status) || intent.status === 'succeeded')
        payment.providerStatus = intent.status;
    if (firstReference && intent.status !== 'canceled') await event(manager, payment, PaymentMessageType.Enabled);
    if (intent.status === 'succeeded' && ![PaymentStatus.Paid, PaymentStatus.Refunded].includes(payment.status)) {
        payment.status = PaymentStatus.Paid;
        await event(manager, payment, PaymentMessageType.Succeeded);
    } else if (intent.status === 'canceled' && payment.status === PaymentStatus.Pending) {
        payment.status = PaymentStatus.Cancelled;
        await event(manager, payment, PaymentMessageType.NotCompleted);
    }
    await manager.getRepository(PaymentEntity).save(payment);
}
async function event(
    manager: EntityManager,
    payment: PaymentEntity,
    type: PaymentMessageType.Enabled | PaymentMessageType.Succeeded | PaymentMessageType.NotCompleted,
): Promise<void> {
    const id = randomUUID();
    const data =
        type === PaymentMessageType.Enabled
            ? { paymentId: payment.id, reservationId: payment.reservationId }
            : type === PaymentMessageType.Succeeded
              ? {
                    paymentId: payment.id,
                    reservationId: payment.reservationId,
                    amountCents: payment.amountCents,
                    currency: payment.currency,
                }
              : { paymentId: payment.id, status: 'CANCELADO', reason: 'PROVIDER_CANCELLED' };
    await manager.getRepository(OutboxEntity).insert({
        id,
        exchange: 'payments.events',
        routingKey: type,
        body: { messageId: id, type, orderId: payment.orderId, occurredAt: new Date().toISOString(), data },
        createdAt: () => 'clock_timestamp()',
    });
}
