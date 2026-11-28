import { randomUUID } from 'node:crypto';
import type { EntityManager } from 'typeorm';
import type { RefundSnapshot } from '../../application/ports/refund-payment.port';
import { PaymentProviderMismatch } from '../../application/payments/payment.error';
import { PaymentStatus } from '../../application/payments/payment';
import { PaymentMessageType } from '../../application/payments/payment-messages';
import { PaymentEntity } from './entities/payment.entity';
import { RefundEntity } from './entities/refund.entity';
import { OutboxEntity } from './entities/outbox.entity';

// Caller locks payment first, then refund, and commits inbox with this result.
export async function persistRefundSnapshot(
    manager: EntityManager,
    payment: PaymentEntity,
    refund: RefundEntity,
    evidence: RefundSnapshot,
): Promise<void> {
    const source = evidence.payment;
    if (
        payment.id !== source.paymentId ||
        payment.orderId !== source.orderId ||
        payment.buyerId !== source.buyerId ||
        payment.reservationId !== source.reservationId ||
        payment.stripePaymentIntentId !== source.id ||
        payment.amountCents !== source.amountCents ||
        payment.currency !== source.currency ||
        refund.id !== evidence.refundId ||
        refund.paymentId !== payment.id ||
        refund.amountCents !== payment.amountCents ||
        refund.currency !== payment.currency ||
        (refund.stripeRefundId && refund.stripeRefundId !== evidence.id) ||
        (!refund.stripeRefundId && !refund.stripeCreationStartedAt) ||
        ![PaymentStatus.Paid, PaymentStatus.Refunded].includes(payment.status)
    )
        throw new PaymentProviderMismatch();
    refund.stripeRefundId = evidence.id;
    if (refund.providerStatus !== 'succeeded') refund.providerStatus = evidence.status;
    if (evidence.status === 'succeeded' && payment.status !== PaymentStatus.Refunded) {
        payment.status = PaymentStatus.Refunded;
        const id = randomUUID();
        await manager.getRepository(OutboxEntity).insert({
            id,
            exchange: 'payments.events',
            routingKey: PaymentMessageType.RefundSucceeded,
            body: {
                messageId: id,
                type: PaymentMessageType.RefundSucceeded,
                orderId: payment.orderId,
                occurredAt: new Date().toISOString(),
                data: { paymentId: payment.id, amountCents: payment.amountCents, currency: payment.currency },
            },
        });
        await manager.getRepository(PaymentEntity).save(payment);
    }
    await manager.getRepository(RefundEntity).save(refund);
}
