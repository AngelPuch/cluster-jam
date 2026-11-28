import { Injectable } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { DataSource, type EntityManager } from 'typeorm';
import type { EnablePaymentStore, PreparedPayment, ProviderIntent } from '../../application/ports/enable-payment.port';
import {
    PaymentCommandConflict,
    PaymentPersistenceUnavailable,
    PaymentProviderMismatch,
} from '../../application/payments/payment.error';
import { PaymentMessageType, type EnablePayment, type PaymentEvent } from '../../application/payments/payment-messages';
import { PaymentStatus } from '../../application/payments/payment';
import { DatabaseReadiness } from './database-readiness.service';
import { PaymentEntity } from './entities/payment.entity';
import { InboxEntity } from './entities/inbox.entity';
import { OutboxEntity } from './entities/outbox.entity';

const CONSUMER = PaymentMessageType.Enable;

@Injectable()
export class TypeormEnablePaymentStore implements EnablePaymentStore {
    constructor(
        private readonly database: DataSource,
        private readonly readiness: DatabaseReadiness,
    ) {}

    async prepare(command: EnablePayment): Promise<PreparedPayment | null> {
        if (!(await this.readiness.check())) throw new PaymentPersistenceUnavailable();
        return this.database.transaction(async (manager) => {
            if (await this.processed(manager, command.messageId)) return null;
            const payments = manager.getRepository(PaymentEntity);
            await payments
                .createQueryBuilder()
                .insert()
                .values({
                    id: randomUUID(),
                    orderId: command.orderId.toLowerCase(),
                    buyerId: command.data.buyerId.toLowerCase(),
                    reservationId: command.data.reservationId.toLowerCase(),
                    reservationExpiresAt: new Date(command.data.reservationExpiresAt),
                    amountCents: command.data.amountCents,
                    currency: command.data.currency,
                })
                .orIgnore()
                .execute();
            const payment = await payments.findOneOrFail({
                where: { orderId: command.orderId.toLowerCase() },
                lock: { mode: 'pessimistic_write' },
            });
            if (await this.processed(manager, command.messageId)) return null;
            this.checkIdentity(payment, command);
            if (payment.stripePaymentIntentId || payment.status !== PaymentStatus.Pending) {
                await this.recordInbox(manager, command.messageId);
                return null;
            }
            const [{ now }] = await manager.query<Array<{ now: Date }>>('SELECT clock_timestamp() AS now');
            if (!payment.stripeCreationStartedAt && now >= payment.reservationExpiresAt) {
                payment.status = PaymentStatus.Cancelled;
                await payments.save(payment);
                await this.result(manager, command, {
                    type: PaymentMessageType.NotCompleted,
                    data: { paymentId: payment.id, status: 'CANCELADO', reason: 'RESERVATION_EXPIRED' },
                });
                return null;
            }
            if (!payment.stripeCreationStartedAt) {
                payment.stripeCreationStartedAt = now;
                await payments.save(payment);
            }
            return {
                id: payment.id,
                orderId: payment.orderId,
                buyerId: payment.buyerId,
                reservationId: payment.reservationId,
                amountCents: payment.amountCents,
                currency: payment.currency,
                stripePaymentIntentId: payment.stripePaymentIntentId,
                creationAgeMs: Math.max(0, now.getTime() - payment.stripeCreationStartedAt.getTime()),
            };
        });
    }

    async complete(command: EnablePayment, paymentId: string, intent: ProviderIntent): Promise<void> {
        await this.database.transaction(async (manager) => {
            const payments = manager.getRepository(PaymentEntity);
            const payment = await payments.findOneOrFail({
                where: { id: paymentId, orderId: command.orderId.toLowerCase() },
                lock: { mode: 'pessimistic_write' },
            });
            if (await this.processed(manager, command.messageId)) return;
            this.checkIdentity(payment, command);
            if (payment.stripePaymentIntentId && payment.stripePaymentIntentId !== intent.id)
                throw new PaymentProviderMismatch();
            if (payment.stripePaymentIntentId || payment.status !== PaymentStatus.Pending) {
                await this.recordInbox(manager, command.messageId);
                return;
            }
            payment.stripePaymentIntentId = intent.id;
            payment.providerStatus = intent.status;
            // Success is accredited by the webhook, never by preparation alone.
            if (intent.status === 'canceled') payment.status = PaymentStatus.Cancelled;
            await payments.save(payment);
            if (payment.status === PaymentStatus.Cancelled) {
                await this.result(manager, command, {
                    type: PaymentMessageType.NotCompleted,
                    data: { paymentId, status: 'CANCELADO', reason: 'PROVIDER_CANCELLED' },
                });
            } else {
                await this.result(manager, command, {
                    type: PaymentMessageType.Enabled,
                    data: { paymentId, reservationId: payment.reservationId },
                });
            }
        });
    }

    private checkIdentity(payment: PaymentEntity, command: EnablePayment): void {
        const data = command.data;
        if (
            payment.buyerId !== data.buyerId.toLowerCase() ||
            payment.reservationId !== data.reservationId.toLowerCase() ||
            payment.amountCents !== data.amountCents ||
            payment.currency !== data.currency ||
            payment.reservationExpiresAt.getTime() !== new Date(data.reservationExpiresAt).getTime()
        ) {
            throw new PaymentCommandConflict();
        }
    }

    private processed(manager: EntityManager, messageId: string): Promise<boolean> {
        return manager.getRepository(InboxEntity).existsBy({ consumer: CONSUMER, messageId: messageId.toLowerCase() });
    }
    private async recordInbox(manager: EntityManager, messageId: string): Promise<void> {
        await manager.getRepository(InboxEntity).insert({ consumer: CONSUMER, messageId: messageId.toLowerCase() });
    }
    private async result(
        manager: EntityManager,
        command: EnablePayment,
        result:
            | Pick<Extract<PaymentEvent, { type: PaymentMessageType.Enabled }>, 'type' | 'data'>
            | Pick<Extract<PaymentEvent, { type: PaymentMessageType.NotCompleted }>, 'type' | 'data'>,
    ): Promise<void> {
        const id = randomUUID();
        const event = {
            messageId: id,
            type: result.type,
            orderId: command.orderId.toLowerCase(),
            occurredAt: new Date().toISOString(),
            data: result.data,
        };
        await manager
            .getRepository(OutboxEntity)
            .insert({ id, exchange: 'payments.events', routingKey: result.type, body: event });
        await this.recordInbox(manager, command.messageId);
    }
}
