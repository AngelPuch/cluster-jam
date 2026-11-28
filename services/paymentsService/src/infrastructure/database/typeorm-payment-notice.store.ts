import { Injectable } from '@nestjs/common';
import { DataSource } from 'typeorm';
import type { PaymentNoticeStore, StripePaymentSnapshot } from '../../application/ports/payment-notice.port';
import { PaymentPersistenceUnavailable, PaymentRecoveryRequired } from '../../application/payments/payment.error';
import { DatabaseReadiness } from './database-readiness.service';
import { PaymentEntity } from './entities/payment.entity';
import { InboxEntity } from './entities/inbox.entity';
import { persistPaymentSnapshot } from './payment-snapshot.writer';
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
            const payment = await manager
                .getRepository(PaymentEntity)
                .findOne({ where: { id: intent.paymentId }, lock: { mode: 'pessimistic_write' } });
            if (!payment) throw new PaymentRecoveryRequired();
            const inbox = manager.getRepository(InboxEntity);
            if (await inbox.existsBy({ consumer: CONSUMER, messageId: eventId })) return;
            await persistPaymentSnapshot(manager, payment, intent);
            await inbox.insert({ consumer: CONSUMER, messageId: eventId });
        });
    }
}
