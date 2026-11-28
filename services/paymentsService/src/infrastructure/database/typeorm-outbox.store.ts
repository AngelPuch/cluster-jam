import { Injectable } from '@nestjs/common';
import { DataSource } from 'typeorm';
import type { OutboxStore, OutgoingPaymentEvent } from '../../application/ports/outbox.port';
import { PaymentPersistenceUnavailable } from '../../application/payments/payment.error';
import { DatabaseReadiness } from './database-readiness.service';
import { OutboxEntity } from './entities/outbox.entity';

@Injectable()
export class TypeormOutboxStore implements OutboxStore {
    constructor(
        private readonly database: DataSource,
        private readonly readiness: DatabaseReadiness,
    ) {}

    async publishNext(publish: (event: OutgoingPaymentEvent) => Promise<void>): Promise<boolean> {
        if (!(await this.readiness.check())) throw new PaymentPersistenceUnavailable();
        return this.database.transaction(async (manager) => {
            // Only this technical outbox row stays locked while waiting for AMQP.
            const repository = manager.getRepository(OutboxEntity);
            const event = await repository
                .createQueryBuilder('event')
                .where('event.status = :status', { status: 'PENDING' })
                .orderBy('event.createdAt', 'ASC')
                .addOrderBy('event.id', 'ASC')
                .take(1)
                .setLock('pessimistic_write')
                .setOnLocked('skip_locked')
                .getOne();
            if (!event) return false;
            await publish(event);
            event.status = 'PUBLISHED';
            event.publishedAt = new Date();
            await repository.save(event);
            return true;
        });
    }
}
