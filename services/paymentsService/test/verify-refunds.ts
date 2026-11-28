import type { INestApplication } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import type Stripe from 'stripe';
import type { DataSource } from 'typeorm';
import request from 'supertest';
import { RefundPaymentService } from '../src/application/payments/refund-payment.service';
import { PaymentCommandConflict, PaymentRecoveryRequired } from '../src/application/payments/payment.error';
import {
    PaymentMessageType,
    type EnablePayment,
    type RefundPayment,
} from '../src/application/payments/payment-messages';
import {
    REFUND_PAYMENT_STORE,
    REFUND_GATEWAY,
    type RefundPaymentStore,
    type RefundGateway,
} from '../src/application/ports/refund-payment.port';
import { DatabaseReadiness } from '../src/infrastructure/database/database-readiness.service';
import { PaymentEntity } from '../src/infrastructure/database/entities/payment.entity';
import { RefundEntity } from '../src/infrastructure/database/entities/refund.entity';
import { OutboxEntity } from '../src/infrastructure/database/entities/outbox.entity';
import { InboxEntity } from '../src/infrastructure/database/entities/inbox.entity';
import { TypeormEnablePaymentStore } from '../src/infrastructure/database/typeorm-enable-payment.store';
import { StripeIntentGateway } from '../src/infrastructure/stripe/stripe-intent.gateway';
import type { StripeFixture } from './stripe-fixture';
export async function verifyRefunds(
    app: INestApplication,
    database: DataSource,
    stripe: Stripe,
    fixture: StripeFixture,
    secret: string,
): Promise<void> {
    const http = app.getHttpServer() as Parameters<typeof request>[0];
    const refunds = app.get(RefundPaymentService);
    const store = app.get<RefundPaymentStore>(REFUND_PAYMENT_STORE);
    const gateway = app.get<RefundGateway>(REFUND_GATEWAY);
    const payments = database.getRepository(PaymentEntity);
    const records = database.getRepository(RefundEntity);
    const outbox = database.getRepository(OutboxEntity);
    const enable = new TypeormEnablePaymentStore(database, new DatabaseReadiness(database));
    function post(remote: Record<string, unknown>, type: string, eventId = 'evt_' + randomUUID().replaceAll('-', '')) {
        const payload = JSON.stringify({
            id: eventId,
            object: 'event',
            livemode: false,
            type,
            data: { object: remote },
        });
        return request(http)
            .post('/api/v1/webhooks/stripe')
            .set('Content-Type', 'application/json')
            .set('Stripe-Signature', stripe.webhooks.generateTestHeaderString({ payload, secret }))
            .send(payload);
    }
    async function paid(): Promise<RefundPayment> {
        const command: EnablePayment = {
            messageId: randomUUID(),
            type: PaymentMessageType.Enable,
            orderId: randomUUID(),
            occurredAt: new Date().toISOString(),
            data: {
                buyerId: randomUUID(),
                reservationId: randomUUID(),
                reservationExpiresAt: new Date(Date.now() + 900000).toISOString(),
                amountCents: 19900,
                currency: 'MXN',
            },
        };
        const prepared = await enable.prepare(command);
        if (!prepared) throw new Error('Expected prepared payment.');
        await new StripeIntentGateway(stripe).ensure(prepared);
        const remote = fixture.intents.get('payment:create:' + command.orderId);
        if (!remote) throw new Error('Missing fixture intent.');
        remote.status = 'succeeded';
        remote.amount_received = 19900;
        await post(remote, 'payment_intent.succeeded').expect(200);
        return {
            ...command,
            messageId: randomUUID(),
            type: PaymentMessageType.Refund,
            data: { paymentId: prepared.id, reason: 'Checkout compensation' },
        };
    }
    async function successCount(orderId: string) {
        return (await outbox.find()).filter(
            (row) => row.body.orderId === orderId && row.routingKey === String(PaymentMessageType.RefundSucceeded),
        ).length;
    }
    fixture.nextRefundStatus = 'pending';
    const first = await paid();
    await refunds.execute(first);
    await refunds.execute(first);
    await refunds.execute({ ...first, messageId: randomUUID() });
    expect((await payments.findOneByOrFail({ id: first.data.paymentId })).status).toBe('PAGADO');
    expect(await successCount(first.orderId)).toBe(0);
    const remote = fixture.refunds.get('payment:refund:' + first.data.paymentId);
    if (!remote) throw new Error('Expected refund.');
    remote.amount = 1;
    await post(remote, 'refund.updated').expect(400);
    remote.amount = 19900;
    remote.status = 'succeeded';
    const eventId = 'evt_' + randomUUID().replaceAll('-', '');
    await post(remote, 'refund.updated', eventId).expect(200);
    await post(remote, 'refund.updated', eventId).expect(200);
    expect((await payments.findOneByOrFail({ id: first.data.paymentId })).status).toBe('REEMBOLSADO');
    expect(await successCount(first.orderId)).toBe(1);
    expect(fixture.refunds.size).toBe(1);
    await refunds.execute({ ...first, messageId: randomUUID() });
    expect(fixture.refunds.size).toBe(1);

    const early = await paid();
    const prepared = await store.prepare(early);
    if (!prepared) throw new Error('Expected refund operation.');
    const stale = await gateway.ensure(prepared);
    const earlyRemote = fixture.refunds.get('payment:refund:' + early.data.paymentId);
    if (!earlyRemote) throw new Error('Missing early refund.');
    earlyRemote.status = 'succeeded';
    await post(earlyRemote, 'refund.updated').expect(200);
    await store.complete(early, stale);
    expect((await records.findOneByOrFail({ paymentId: early.data.paymentId })).providerStatus).toBe('succeeded');
    expect((await payments.findOneByOrFail({ id: early.data.paymentId })).status).toBe('REEMBOLSADO');
    expect(await successCount(early.orderId)).toBe(1);

    fixture.nextRefundStatus = 'failed';
    const failed = await paid();
    await expect(refunds.execute(failed)).rejects.toBeInstanceOf(PaymentRecoveryRequired);
    await expect(refunds.execute(failed)).rejects.toBeInstanceOf(PaymentRecoveryRequired);
    expect((await records.findOneByOrFail({ paymentId: failed.data.paymentId })).stripeRefundId).toMatch(/^re_/);
    expect((await payments.findOneByOrFail({ id: failed.data.paymentId })).status).toBe('PAGADO');
    expect(await successCount(failed.orderId)).toBe(0);
    expect(
        await database.getRepository(InboxEntity).existsBy({ consumer: failed.type, messageId: failed.messageId }),
    ).toBe(false);
    await expect(refunds.execute({ ...failed, messageId: randomUUID(), orderId: randomUUID() })).rejects.toBeInstanceOf(
        PaymentCommandConflict,
    );
    expect(fixture.refunds.size).toBe(3);
}
