import { Injectable } from '@nestjs/common';
import { DataSource } from 'typeorm';
import type { CancelPaymentStore, StripePaymentReference } from '../../application/ports/cancel-payment.port';
import type { StripePaymentSnapshot } from '../../application/ports/payment-notice.port';
import {
    PaymentCommandConflict,
    PaymentPersistenceUnavailable,
    PaymentRecoveryRequired,
} from '../../application/payments/payment.error';
import { PaymentMessageType, type CancelPayment } from '../../application/payments/payment-messages';
import { PaymentStatus } from '../../application/payments/payment';
import { DatabaseReadiness } from './database-readiness.service';
import { PaymentEntity } from './entities/payment.entity';
import { InboxEntity } from './entities/inbox.entity';
import { persistPaymentSnapshot } from './payment-snapshot.writer';
const CONSUMER = PaymentMessageType.Cancel;
@Injectable()
export class TypeormCancelPaymentStore implements CancelPaymentStore {
    constructor(
        private readonly database: DataSource,
        private readonly readiness: DatabaseReadiness,
    ) {}
    async prepare(command: CancelPayment): Promise<StripePaymentReference | null> {
        if (!(await this.readiness.check())) throw new PaymentPersistenceUnavailable();
        return this.database.transaction(async (manager) => {
            const payment = await manager.getRepository(PaymentEntity).findOne({
                where: { id: command.data.paymentId.toLowerCase(), orderId: command.orderId.toLowerCase() },
                lock: { mode: 'pessimistic_write' },
            });
            if (!payment) throw new PaymentCommandConflict();
            const inbox = manager.getRepository(InboxEntity);
            if (await inbox.existsBy({ consumer: CONSUMER, messageId: command.messageId.toLowerCase() })) return null;
            if (payment.status !== PaymentStatus.Pending) {
                // The original paid/cancelled/refunded result is already in outbox.
                await inbox.insert({ consumer: CONSUMER, messageId: command.messageId.toLowerCase() });
                return null;
            }
            if (!payment.stripePaymentIntentId) throw new PaymentRecoveryRequired();
            return {
                id: payment.stripePaymentIntentId,
                paymentId: payment.id,
                orderId: payment.orderId,
                buyerId: payment.buyerId,
                reservationId: payment.reservationId,
                amountCents: payment.amountCents,
                currency: payment.currency,
            };
        });
    }
    async complete(command: CancelPayment, intent: StripePaymentSnapshot): Promise<void> {
        await this.database.transaction(async (manager) => {
            const payment = await manager.getRepository(PaymentEntity).findOne({
                where: { id: command.data.paymentId.toLowerCase(), orderId: command.orderId.toLowerCase() },
                lock: { mode: 'pessimistic_write' },
            });
            if (!payment) throw new PaymentCommandConflict();
            const inbox = manager.getRepository(InboxEntity);
            if (await inbox.existsBy({ consumer: CONSUMER, messageId: command.messageId.toLowerCase() })) return;
            await persistPaymentSnapshot(manager, payment, intent);
            await inbox.insert({ consumer: CONSUMER, messageId: command.messageId.toLowerCase() });
        });
    }
}
