import { Injectable } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { DataSource } from 'typeorm';
import type { RefundPaymentStore, PreparedRefund, RefundSnapshot } from '../../application/ports/refund-payment.port';
import type { RefundPayment } from '../../application/payments/payment-messages';
import { PaymentMessageType } from '../../application/payments/payment-messages';
import {
    PaymentCommandConflict,
    PaymentPersistenceUnavailable,
    PaymentRecoveryRequired,
} from '../../application/payments/payment.error';
import { PaymentStatus } from '../../application/payments/payment';
import { DatabaseReadiness } from './database-readiness.service';
import { PaymentEntity } from './entities/payment.entity';
import { RefundEntity } from './entities/refund.entity';
import { InboxEntity } from './entities/inbox.entity';
import { persistRefundSnapshot } from './refund-snapshot.writer';
const CONSUMER = PaymentMessageType.Refund;
@Injectable()
export class TypeormRefundStore implements RefundPaymentStore {
    constructor(
        private readonly database: DataSource,
        private readonly readiness: DatabaseReadiness,
    ) {}
    async prepare(command: RefundPayment): Promise<PreparedRefund | null> {
        if (!(await this.readiness.check())) throw new PaymentPersistenceUnavailable();
        return this.database.transaction(async (manager) => {
            const payment = await manager.getRepository(PaymentEntity).findOne({
                where: { id: command.data.paymentId.toLowerCase(), orderId: command.orderId.toLowerCase() },
                lock: { mode: 'pessimistic_write' },
            });
            if (!payment) throw new PaymentCommandConflict();
            const inbox = manager.getRepository(InboxEntity);
            if (await inbox.existsBy({ consumer: CONSUMER, messageId: command.messageId.toLowerCase() })) return null;
            if (payment.status === PaymentStatus.Refunded) {
                await inbox.insert({ consumer: CONSUMER, messageId: command.messageId.toLowerCase() });
                return null;
            }
            if (payment.status !== PaymentStatus.Paid || !payment.stripePaymentIntentId)
                throw new PaymentCommandConflict();
            const refunds = manager.getRepository(RefundEntity);
            await refunds
                .createQueryBuilder()
                .insert()
                .values({
                    id: randomUUID(),
                    paymentId: payment.id,
                    amountCents: payment.amountCents,
                    currency: payment.currency,
                    reason: command.data.reason,
                })
                .orIgnore()
                .execute();
            const refund = await refunds.findOneOrFail({
                where: { paymentId: payment.id },
                lock: { mode: 'pessimistic_write' },
            });
            const [{ now }] = await manager.query<Array<{ now: Date }>>('SELECT clock_timestamp() AS now');
            if (!refund.stripeCreationStartedAt) {
                refund.stripeCreationStartedAt = now;
                await refunds.save(refund);
            }
            return {
                id: refund.id,
                stripeRefundId: refund.stripeRefundId,
                creationAgeMs: Math.max(0, now.getTime() - refund.stripeCreationStartedAt.getTime()),
                payment: {
                    id: payment.stripePaymentIntentId,
                    paymentId: payment.id,
                    orderId: payment.orderId,
                    buyerId: payment.buyerId,
                    reservationId: payment.reservationId,
                    amountCents: payment.amountCents,
                    currency: payment.currency,
                },
            };
        });
    }
    async complete(command: RefundPayment, evidence: RefundSnapshot): Promise<void> {
        await this.database.transaction(async (manager) => {
            const payment = await manager.getRepository(PaymentEntity).findOne({
                where: { id: command.data.paymentId.toLowerCase(), orderId: command.orderId.toLowerCase() },
                lock: { mode: 'pessimistic_write' },
            });
            if (!payment) throw new PaymentCommandConflict();
            const inbox = manager.getRepository(InboxEntity);
            if (await inbox.existsBy({ consumer: CONSUMER, messageId: command.messageId.toLowerCase() })) return;
            const refund = await manager
                .getRepository(RefundEntity)
                .findOne({ where: { paymentId: payment.id }, lock: { mode: 'pessimistic_write' } });
            if (!refund) throw new PaymentRecoveryRequired();
            await persistRefundSnapshot(manager, payment, refund, evidence);
            if (!['failed', 'canceled'].includes(evidence.status))
                await inbox.insert({ consumer: CONSUMER, messageId: command.messageId.toLowerCase() });
        });
    }
}
