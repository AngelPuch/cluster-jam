import { Injectable } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { DataSource, type EntityManager } from 'typeorm';
import type { PaymentNoticeStore, StripePaymentSnapshot } from '../../application/ports/payment-notice.port';
import {
    PaymentPersistenceUnavailable,
    PaymentProviderMismatch,
    PaymentRecoveryRequired,
} from '../../application/payments/payment.error';
import { PaymentMessageType } from '../../application/payments/payment-messages';
import { PaymentStatus } from '../../application/payments/payment';
import { DatabaseReadiness } from './database-readiness.service';
import { PaymentEntity } from './entities/payment.entity';
import { InboxEntity } from './entities/inbox.entity';
import { OutboxEntity } from './entities/outbox.entity';

const CONSUMER = 'stripe-payment-webhook';
@Injectable()
export class TypeormPaymentNoticeStore implements PaymentNoticeStore {
    constructor(
        private readonly database: DataSource,
        private readonly readiness: DatabaseReadiness,
    ) {}

    async processed(eventId: string): Promise<boolean> {
        if (!(await this.readiness.check())) throw new PaymentPersistenceUnavailable();
        return this.database.getRepository(InboxEntity).existsBy({ consumer: CONSUMER, messageId: eventId });
    }

    async apply(eventId: string, intent: StripePaymentSnapshot): Promise<void> {
        await this.database.transaction(async (manager) => {
            const payments = manager.getRepository(PaymentEntity);
            const payment = await payments.findOne({
                where: { id: intent.paymentId },
                lock: { mode: 'pessimistic_write' },
            });
            if (!payment) throw new PaymentRecoveryRequired();
            const inbox = manager.getRepository(InboxEntity);
            if (await inbox.existsBy({ consumer: CONSUMER, messageId: eventId })) return;
            if (
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
            // A later preparation/decline must not undo credited money.
            if (
                ![PaymentStatus.Paid, PaymentStatus.Refunded].includes(payment.status) ||
                intent.status === 'succeeded'
            ) {
                payment.providerStatus = intent.status;
            }
            if (firstReference && intent.status !== 'canceled')
                await this.event(manager, payment, PaymentMessageType.Enabled);
            if (
                intent.status === 'succeeded' &&
                ![PaymentStatus.Paid, PaymentStatus.Refunded].includes(payment.status)
            ) {
                payment.status = PaymentStatus.Paid;
                await this.event(manager, payment, PaymentMessageType.Succeeded);
            } else if (intent.status === 'canceled' && payment.status === PaymentStatus.Pending) {
                payment.status = PaymentStatus.Cancelled;
                await this.event(manager, payment, PaymentMessageType.NotCompleted);
            }
            await payments.save(payment);
            await inbox.insert({ consumer: CONSUMER, messageId: eventId });
        });
    }

    private async event(
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
}
