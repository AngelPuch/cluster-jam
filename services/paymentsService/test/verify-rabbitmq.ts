import { ConfigService } from '@nestjs/config';
import { connect, type ChannelModel, type Channel, type ConfirmChannel, type GetMessage } from 'amqplib';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import type { DataSource } from 'typeorm';
import { PublishOutboxService } from '../src/application/outbox/publish-outbox.service';
import { EnablePaymentService } from '../src/application/payments/enable-payment.service';
import { PaymentMessageType, type EnablePayment } from '../src/application/payments/payment-messages';
import { DatabaseReadiness } from '../src/infrastructure/database/database-readiness.service';
import { InboxEntity } from '../src/infrastructure/database/entities/inbox.entity';
import { OutboxEntity } from '../src/infrastructure/database/entities/outbox.entity';
import { PaymentEntity } from '../src/infrastructure/database/entities/payment.entity';
import { TypeormEnablePaymentStore } from '../src/infrastructure/database/typeorm-enable-payment.store';
import { TypeormOutboxStore } from '../src/infrastructure/database/typeorm-outbox.store';
import { PaymentBroker, PaymentBrokerUnavailable } from '../src/infrastructure/messaging/payment-broker';
import { JsonLogger } from '../src/infrastructure/observability/json-logger.service';
import { TraceContextService } from '../src/infrastructure/observability/trace-context.service';
import { StripeIntentGateway } from '../src/infrastructure/stripe/stripe-intent.gateway';
import { PaymentCommandConsumer } from '../src/interfaces/messaging/payment-command.consumer';
import { PaymentsMessagingWorker } from '../src/interfaces/workers/payments-messaging.worker';
import { StripeFixture } from './stripe-fixture';

async function waitFor(check: () => Promise<boolean>): Promise<void> {
    for (let count = 0; count < 100; count++) {
        if (await check()) return;
        await delay(50);
    }
    throw new Error('Expected broker/database result did not arrive.');
}
async function take(channel: Channel, queue: string): Promise<GetMessage> {
    for (let count = 0; count < 100; count++) {
        const message = await channel.get(queue, { noAck: true });
        if (message) return message;
        await delay(50);
    }
    throw new Error('Expected queue delivery did not arrive.');
}
async function send(
    channel: ConfirmChannel,
    input: EnablePayment,
    content = Buffer.from(JSON.stringify(input)),
): Promise<void> {
    await new Promise<void>((resolve, reject) =>
        channel.publish(
            'payments.commands',
            input.type,
            content,
            {
                mandatory: true,
                persistent: true,
                contentType: 'application/json',
                messageId: input.messageId,
                correlationId: input.orderId,
                type: input.type,
            },
            (error: unknown) => (error ? reject(new Error('Test command was not confirmed.')) : resolve()),
        ),
    );
}

export async function verifyRabbitMq(database: DataSource): Promise<void> {
    const adminUri = process.env.PAYMENTS_TEST_RABBITMQ_URI ?? '';
    const runtimeUri = process.env.RABBITMQ_URI ?? '';
    for (const value of [adminUri, runtimeUri]) {
        const uri = new URL(value);
        if (!['127.0.0.1', 'localhost'].includes(uri.hostname) || uri.pathname !== '/clusterjam') {
            throw new Error('Use an explicitly enabled disposable loopback broker.');
        }
    }
    const config = new ConfigService({ RABBITMQ_ENABLED: true, RABBITMQ_URI: runtimeUri });
    const logger = new JsonLogger();
    const traces = new TraceContextService();
    const broker = new PaymentBroker(config, logger, traces);
    const readiness = new DatabaseReadiness(database);
    const publication = new PublishOutboxService(new TypeormOutboxStore(database, readiness), broker);
    const fixture = new StripeFixture();
    let admin: ChannelModel | undefined;
    let worker: PaymentsMessagingWorker | undefined;
    try {
        const service = new EnablePaymentService(
            new TypeormEnablePaymentStore(database, readiness),
            new StripeIntentGateway(await fixture.open()),
        );
        const failedOrder = randomUUID();
        let attempts = 0;
        const consumer = new PaymentCommandConsumer(
            {
                execute: async (input) => {
                    if (input.orderId === failedOrder) {
                        attempts++;
                        throw new Error('Simulated transient failure');
                    }
                    await service.execute(input);
                },
            },
            logger,
            traces,
        );
        worker = new PaymentsMessagingWorker(config, broker, consumer, publication, logger);
        admin = await connect(adminUri);
        admin.on('error', () => undefined);
        const channel = await admin.createConfirmChannel();
        channel.on('error', () => undefined);
        const command: EnablePayment = {
            messageId: randomUUID(),
            type: PaymentMessageType.Enable,
            orderId: randomUUID(),
            occurredAt: new Date().toISOString(),
            data: {
                reservationId: randomUUID(),
                buyerId: randomUUID(),
                reservationExpiresAt: new Date(Date.now() + 900000).toISOString(),
                amountCents: 19900,
                currency: 'MXN',
            },
        };

        await worker.tick();
        while (await channel.get('orders.checkout.v1', { noAck: true })) {
            /* Drain earlier schema fixture events. */
        }
        expect((await channel.checkQueue('payments.commands.v1')).consumerCount).toBe(0);
        await send(channel, command);
        expect((await channel.checkQueue('payments.commands.v1')).messageCount).toBe(1);
        config.set('STRIPE_SECRET_KEY', 'sk_test_fixtureOnly');
        await worker.tick();
        const inbox = database.getRepository(InboxEntity);
        await waitFor(() => inbox.existsBy({ consumer: command.type, messageId: command.messageId }));
        await broker.disconnect();
        await worker.tick();
        await send(channel, command);
        const payment = await database.getRepository(PaymentEntity).findOneByOrFail({ orderId: command.orderId });
        expect(payment.status).toBe('PENDIENTE');
        expect(fixture.intents.size).toBe(1);

        // An unroutable confirmed publish must leave the same outbox ID pending.
        const outbox = database.getRepository(OutboxEntity);
        const pending = (await outbox.find()).find((row) => row.body.orderId === command.orderId);
        if (!pending) throw new Error('Payment event was not persisted.');
        // tick above may already have published the first result. Reuse that
        // committed event as a new pending delivery to model a lost SQL commit.
        await outbox.update(pending.id, { status: 'PENDING', publishedAt: null });
        while (await channel.get('orders.checkout.v1', { noAck: true })) {
            /* Drain the original delivery. */
        }
        await channel.unbindQueue('orders.checkout.v1', 'payments.events', PaymentMessageType.Enabled);
        try {
            await expect(publication.runBatch()).rejects.toBeInstanceOf(PaymentBrokerUnavailable);
            expect((await outbox.findOneByOrFail({ id: pending.id })).status).toBe('PENDING');
        } finally {
            await channel.bindQueue('orders.checkout.v1', 'payments.events', PaymentMessageType.Enabled);
        }
        await publication.runBatch();
        const published = await take(channel, 'orders.checkout.v1');
        expect(published.properties.messageId).toBe(pending.id);
        expect(published.properties.deliveryMode).toBe(2);
        expect(published.properties.correlationId).toBe(command.orderId);
        expect((await outbox.findOneByOrFail({ id: pending.id })).status).toBe('PUBLISHED');
        expect(published.content.toString()).not.toContain('secret');

        const invalid = { ...command, messageId: randomUUID() };
        await send(channel, invalid, Buffer.from('{invalid'));
        const dead = await take(channel, 'payments.commands.v1.dlq');
        expect(dead.properties.messageId).toBe(invalid.messageId);
        expect(dead.content.toString()).toBe('{invalid');
        const technical = { ...command, messageId: randomUUID(), orderId: failedOrder };
        await send(channel, technical);
        expect((await take(channel, 'payments.commands.v1.dlq')).properties.messageId).toBe(technical.messageId);
        expect(attempts).toBe(3);
        expect(await inbox.existsBy({ consumer: technical.type, messageId: technical.messageId })).toBe(false);
        expect(await outbox.countBy({ routingKey: PaymentMessageType.Enabled })).toBe(3);
        expect(fixture.requests).toHaveLength(1);
    } finally {
        await worker?.beforeApplicationShutdown();
        await broker.onApplicationShutdown();
        await admin?.close().catch(() => undefined);
        await fixture.close();
    }
}
