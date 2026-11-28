import { randomUUID } from 'node:crypto';
import type { DataSource } from 'typeorm';
import { EnablePaymentService } from '../src/application/payments/enable-payment.service';
import { PaymentMessageType, type EnablePayment } from '../src/application/payments/payment-messages';
import { PaymentCommandConflict, PaymentProviderUnavailable } from '../src/application/payments/payment.error';
import { PaymentStatus } from '../src/application/payments/payment';
import { DatabaseReadiness } from '../src/infrastructure/database/database-readiness.service';
import { PaymentEntity } from '../src/infrastructure/database/entities/payment.entity';
import { InboxEntity } from '../src/infrastructure/database/entities/inbox.entity';
import { OutboxEntity } from '../src/infrastructure/database/entities/outbox.entity';
import { TypeormEnablePaymentStore } from '../src/infrastructure/database/typeorm-enable-payment.store';
import { StripeIntentGateway } from '../src/infrastructure/stripe/stripe-intent.gateway';
import { StripeFixture } from './stripe-fixture';

function command(expiry = new Date(Date.now() + 900000)): EnablePayment {
    return {
        messageId: randomUUID(),
        type: PaymentMessageType.Enable,
        orderId: randomUUID(),
        occurredAt: new Date().toISOString(),
        data: {
            reservationId: randomUUID(),
            reservationExpiresAt: expiry.toISOString(),
            buyerId: randomUUID(),
            amountCents: 19900,
            currency: 'MXN',
        },
    };
}

export async function verifyEnablePayment(database: DataSource): Promise<void> {
    const fixture = new StripeFixture();
    try {
        const gateway = new StripeIntentGateway(await fixture.open());
        const store = new TypeormEnablePaymentStore(database, new DatabaseReadiness(database));
        const service = new EnablePaymentService(store, gateway);
        const payments = database.getRepository(PaymentEntity);
        const outbox = database.getRepository(OutboxEntity);
        const inbox = database.getRepository(InboxEntity);
        const input = command();
        // Stripe retries one closed connection even with maxNetworkRetries=0.
        fixture.dropCreateResponses = 2;
        await expect(service.execute(input)).rejects.toBeInstanceOf(PaymentProviderUnavailable);
        const pending = await payments.findOneByOrFail({ orderId: input.orderId });
        expect(pending.stripeCreationStartedAt).toBeInstanceOf(Date);
        expect(pending.stripePaymentIntentId).toBeNull();
        expect(await inbox.existsBy({ consumer: input.type, messageId: input.messageId })).toBe(false);

        const prepared = await store.prepare(input);
        if (!prepared) throw new Error('An uncertain operation must remain recoverable.');
        const intent = await gateway.ensure(prepared);
        // A failed SQL finalization must leave both inbox and outbox uncommitted.
        await expect(store.complete(input, prepared.id, { ...intent, status: 'x'.repeat(65) })).rejects.toMatchObject({
            code: '22001',
        });
        expect((await payments.findOneByOrFail({ id: prepared.id })).stripePaymentIntentId).toBeNull();
        expect(await outbox.count()).toBe(0);
        expect(await inbox.existsBy({ consumer: input.type, messageId: input.messageId })).toBe(false);

        await service.execute(input);
        await service.execute(input);
        await service.execute({ ...input, messageId: randomUUID() });
        const enabled = await payments.findOneByOrFail({ id: prepared.id });
        expect(enabled.status).toBe(PaymentStatus.Pending);
        expect(enabled.stripePaymentIntentId).toBe(intent.id);
        expect(fixture.intents.size).toBe(1);
        const events = await outbox.find();
        expect(events).toHaveLength(1);
        expect(events[0].status).toBe('PENDING');
        expect(events[0].body).toMatchObject({
            type: PaymentMessageType.Enabled,
            orderId: input.orderId,
            data: { paymentId: enabled.id, reservationId: input.data.reservationId },
        });
        expect(JSON.stringify(events)).not.toContain('secret');
        await expect(
            service.execute({ ...input, messageId: randomUUID(), data: { ...input.data, amountCents: 1 } }),
        ).rejects.toBeInstanceOf(PaymentCommandConflict);

        const expired = command(new Date(Date.now() - 60000));
        const calls = fixture.requests.length;
        await service.execute(expired);
        expect(fixture.requests).toHaveLength(calls);
        expect((await payments.findOneByOrFail({ orderId: expired.orderId })).status).toBe(PaymentStatus.Cancelled);
        expect(await outbox.countBy({ routingKey: PaymentMessageType.NotCompleted })).toBe(1);

        // An earlier attempt may have reached Stripe before the reservation expired.
        const uncertain = command(new Date(Date.now() - 60000));
        const prior = await payments.save(
            payments.create({
                id: randomUUID(),
                orderId: uncertain.orderId,
                ...uncertain.data,
                reservationExpiresAt: new Date(uncertain.data.reservationExpiresAt),
                stripeCreationStartedAt: new Date(Date.now() - 120000),
            }),
        );
        await gateway.ensure({ ...prior, creationAgeMs: 120000 });
        await service.execute(uncertain);
        expect((await payments.findOneByOrFail({ id: prior.id })).stripePaymentIntentId).not.toBeNull();
        expect(await outbox.countBy({ routingKey: PaymentMessageType.NotCompleted })).toBe(1);
        expect(fixture.intents.size).toBe(2);
    } finally {
        await fixture.close();
    }
}
