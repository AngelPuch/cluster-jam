import { Injectable } from '@nestjs/common';
import { DataSource } from 'typeorm';
import type { RefundNoticeStore, RefundSnapshot } from '../../application/ports/refund-payment.port';
import { PaymentPersistenceUnavailable, PaymentRecoveryRequired } from '../../application/payments/payment.error';
import { DatabaseReadiness } from './database-readiness.service';
import { PaymentEntity } from './entities/payment.entity';
import { RefundEntity } from './entities/refund.entity';
import { InboxEntity } from './entities/inbox.entity';
import { persistRefundSnapshot } from './refund-snapshot.writer';
const CONSUMER = 'stripe-refund-webhook';
@Injectable()
export class TypeormRefundNoticeStore implements RefundNoticeStore {
    constructor(
        private readonly database: DataSource,
        private readonly readiness: DatabaseReadiness,
    ) {}
    async processed(eventId: string): Promise<boolean> {
        if (!(await this.readiness.check())) throw new PaymentPersistenceUnavailable();
        return this.database.getRepository(InboxEntity).existsBy({ consumer: CONSUMER, messageId: eventId });
    }
    async apply(eventId: string, evidence: RefundSnapshot): Promise<void> {
        await this.database.transaction(async (manager) => {
            const payment = await manager
                .getRepository(PaymentEntity)
                .findOne({ where: { id: evidence.payment.paymentId }, lock: { mode: 'pessimistic_write' } });
            if (!payment) throw new PaymentRecoveryRequired();
            const inbox = manager.getRepository(InboxEntity);
            if (await inbox.existsBy({ consumer: CONSUMER, messageId: eventId })) return;
            const refund = await manager.getRepository(RefundEntity).findOne({
                where: { id: evidence.refundId, paymentId: payment.id },
                lock: { mode: 'pessimistic_write' },
            });
            if (!refund) throw new PaymentRecoveryRequired();
            await persistRefundSnapshot(manager, payment, refund, evidence);
            await inbox.insert({ consumer: CONSUMER, messageId: eventId });
        });
    }
}
