import { Test } from '@nestjs/testing';
import { APP_FILTER } from '@nestjs/core';
import type { INestApplication } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { DataSource } from 'typeorm';
import { randomUUID } from 'node:crypto';
import request from 'supertest';
import { PaymentMessageType, type EnablePayment } from '../src/application/payments/payment-messages';
import { DatabaseReadiness } from '../src/infrastructure/database/database-readiness.service';
import { PaymentEntity } from '../src/infrastructure/database/entities/payment.entity';
import { OutboxEntity } from '../src/infrastructure/database/entities/outbox.entity';
import { InboxEntity } from '../src/infrastructure/database/entities/inbox.entity';
import { TypeormEnablePaymentStore } from '../src/infrastructure/database/typeorm-enable-payment.store';
import { ObservabilityModule } from '../src/infrastructure/observability/observability.module';
import { STRIPE_CLIENT, StripeIntentGateway } from '../src/infrastructure/stripe/stripe-intent.gateway';
import { configureHttpApplication } from '../src/interfaces/http/http.setup';
import { ProblemDetailsFilter } from '../src/interfaces/http/common/problem-details.filter';
import { PaymentsModule } from '../src/payments.module';
import { PaymentStatus } from '../src/application/payments/payment';
import { StripeFixture } from './stripe-fixture';

export async function verifyPaymentWebhook(database: DataSource): Promise<void> {
    const fixture = new StripeFixture();
    const stripe = await fixture.open();
    const secret = 'whsec_fixtureOnly';
    const readiness = new DatabaseReadiness(database);
    let app: INestApplication | undefined;
    try {
        const module = await Test.createTestingModule({
            imports: [
                ConfigModule.forRoot({ isGlobal: true, ignoreEnvFile: true }),
                ObservabilityModule,
                PaymentsModule,
            ],
            providers: [{ provide: APP_FILTER, useClass: ProblemDetailsFilter }],
        })
            .overrideProvider(ConfigService)
            .useValue(new ConfigService({ STRIPE_WEBHOOK_SECRET: secret }))
            .overrideProvider(DataSource)
            .useValue(database)
            .overrideProvider(DatabaseReadiness)
            .useValue({ check: () => readiness.check() })
            .overrideProvider(STRIPE_CLIENT)
            .useValue(stripe)
            .compile();
        app = module.createNestApplication({ logger: false, rawBody: true });
        configureHttpApplication(app);
        await app.init();
        const http = app.getHttpServer() as Parameters<typeof request>[0];
        const payments = database.getRepository(PaymentEntity);
        const outbox = database.getRepository(OutboxEntity);
        const inbox = database.getRepository(InboxEntity);
        const enable = new TypeormEnablePaymentStore(database, readiness);
        const gateway = new StripeIntentGateway(stripe);
        async function prepare() {
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
            if (!prepared) throw new Error('Expected a newly prepared payment.');
            const intent = await gateway.ensure(prepared);
            const remote = fixture.intents.get('payment:create:' + command.orderId);
            if (!remote) throw new Error('Expected a provider fixture intent.');
            return { command, prepared, intent, remote };
        }
        function notice(remote: Record<string, unknown>, type = 'payment_intent.succeeded') {
            return JSON.stringify({
                id: 'evt_' + randomUUID().replaceAll('-', ''),
                object: 'event',
                livemode: false,
                type,
                data: { object: { ...remote } },
            });
        }
        function post(payload: string) {
            return request(http)
                .post('/api/v1/webhooks/stripe')
                .set('Content-Type', 'application/json')
                .set('Stripe-Signature', stripe.webhooks.generateTestHeaderString({ payload, secret }))
                .send(payload);
        }
        async function results(orderId: string) {
            return (await outbox.find({ order: { createdAt: 'ASC', id: 'ASC' } })).filter(
                (row) => row.body.orderId === orderId,
            );
        }

        const first = await prepare();
        first.remote.status = 'succeeded';
        first.remote.amount_received = 19900;
        const payload = notice(first.remote);
        await post(payload).expect(200);
        const reads = fixture.retrievals.length;
        await post(payload).expect(200);
        expect(fixture.retrievals).toHaveLength(reads);
        expect((await payments.findOneByOrFail({ id: first.prepared.id })).status).toBe('PAGADO');
        expect((await results(first.command.orderId)).map((row) => row.routingKey)).toEqual([
            PaymentMessageType.Enabled,
            PaymentMessageType.Succeeded,
        ]);
        // The original preparation finishes after the webhook without demotion.
        await enable.complete(first.command, first.prepared.id, first.intent);
        await post(
            notice({ ...first.remote, status: 'requires_payment_method' }, 'payment_intent.payment_failed'),
        ).expect(200);
        expect((await payments.findOneByOrFail({ id: first.prepared.id })).status).toBe('PAGADO');
        await payments.update(first.prepared.id, { status: PaymentStatus.Refunded });
        await post(notice(first.remote)).expect(200);
        expect((await payments.findOneByOrFail({ id: first.prepared.id })).status).toBe('REEMBOLSADO');
        expect(await results(first.command.orderId)).toHaveLength(2);
        expect(JSON.stringify(await results(first.command.orderId))).not.toContain('secret');

        const cancelled = await prepare();
        cancelled.remote.status = 'canceled';
        cancelled.remote.amount_received = 1;
        await post(notice(cancelled.remote, 'payment_intent.canceled')).expect(400);
        expect((await payments.findOneByOrFail({ id: cancelled.prepared.id })).status).toBe('PENDIENTE');
        expect(await results(cancelled.command.orderId)).toHaveLength(0);
        cancelled.remote.amount_received = 0;
        await post(notice(cancelled.remote, 'payment_intent.canceled')).expect(200);
        await post(notice(cancelled.remote, 'payment_intent.canceled')).expect(200);
        expect((await payments.findOneByOrFail({ id: cancelled.prepared.id })).status).toBe('CANCELADO');
        expect((await results(cancelled.command.orderId)).map((row) => row.routingKey)).toEqual([
            PaymentMessageType.NotCompleted,
        ]);

        const declined = await prepare();
        await post(notice(declined.remote, 'payment_intent.payment_failed')).expect(200);
        expect((await payments.findOneByOrFail({ id: declined.prepared.id })).status).toBe('PENDIENTE');
        expect((await results(declined.command.orderId)).map((row) => row.routingKey)).toEqual([
            PaymentMessageType.Enabled,
        ]);
        declined.remote.amount = 19901;
        const mismatch = notice(declined.remote, 'payment_intent.payment_failed');
        await post(mismatch).expect(400);
        const mismatchId = (JSON.parse(mismatch) as { id: string }).id;
        expect(await inbox.existsBy({ consumer: 'stripe-payment-webhook', messageId: mismatchId })).toBe(false);
        expect(await results(declined.command.orderId)).toHaveLength(1);
    } finally {
        await app?.close();
        await fixture.close();
    }
}
