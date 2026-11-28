import { Injectable, type OnApplicationShutdown } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { readFileSync } from 'node:fs';
import { connect, type Channel, type ChannelModel, type ConfirmChannel } from 'amqplib';
import type { OutgoingPaymentEvent, PaymentEventPublisher } from '../../application/ports/outbox.port';
import { JsonLogger } from '../observability/json-logger.service';
import { TraceContextService } from '../observability/trace-context.service';

export class PaymentBrokerUnavailable extends Error {
    constructor() {
        super('PAYMENT_BROKER_UNAVAILABLE');
    }
}

@Injectable()
export class PaymentBroker implements PaymentEventPublisher, OnApplicationShutdown {
    private connection?: ChannelModel;
    private consumer?: Channel;
    private publisher?: ConfirmChannel;
    private opening?: Promise<Channel>;
    private stopping = false;

    constructor(
        private readonly config: ConfigService,
        private readonly logger: JsonLogger,
        private readonly traces: TraceContextService,
    ) {}

    async open(): Promise<Channel> {
        if (this.stopping) throw new PaymentBrokerUnavailable();
        if (this.consumer) return this.consumer;
        this.opening ??= this.connect().finally(() => {
            this.opening = undefined;
        });
        return this.opening;
    }

    private async connect(): Promise<Channel> {
        let connection: ChannelModel | undefined;
        try {
            const uri = new URL(this.config.getOrThrow<string>('RABBITMQ_URI'));
            uri.searchParams.set('heartbeat', '10');
            const caPath = this.config.get<string>('RABBITMQ_CA_PATH');
            connection = await connect(uri.toString(), {
                timeout: 3000,
                rejectUnauthorized: true,
                ...(uri.protocol === 'amqps:'
                    ? { servername: uri.hostname, ...(caPath ? { ca: readFileSync(caPath) } : {}) }
                    : {}),
            });
            const current = connection;
            this.connection = current;
            const lost = () => {
                if (this.connection === current) void this.disconnect();
            };
            current.on('error', lost);
            current.on('close', lost);
            const consumer = await current.createChannel();
            consumer.on('error', lost);
            consumer.on('close', lost);
            const publisher = await current.createConfirmChannel();
            publisher.on('error', lost);
            publisher.on('close', lost);
            await consumer.prefetch(1);
            if (this.connection !== current || this.stopping) throw new PaymentBrokerUnavailable();
            this.consumer = consumer;
            this.publisher = publisher;
            this.logger.log({ event: 'payments.broker.connected' });
            return consumer;
        } catch {
            if (connection && this.connection === connection) await this.disconnect();
            throw new PaymentBrokerUnavailable();
        }
    }

    async publish(event: OutgoingPaymentEvent): Promise<void> {
        await this.open();
        const channel = this.publisher;
        if (
            !channel ||
            event.exchange !== 'payments.events' ||
            event.body.messageId !== event.id ||
            event.body.type !== event.routingKey ||
            typeof event.body.orderId !== 'string'
        )
            throw new PaymentBrokerUnavailable();
        await this.traces.runProducer(async () => {
            await new Promise<void>((resolve, reject) => {
                let returned = false;
                const onReturn = () => {
                    returned = true;
                };
                const onClose = () => finish(new PaymentBrokerUnavailable());
                const timer = setTimeout(() => {
                    finish(new PaymentBrokerUnavailable());
                    if (this.publisher === channel) void this.disconnect();
                }, 3000);
                const finish = (error?: Error) => {
                    clearTimeout(timer);
                    channel.removeListener('return', onReturn);
                    channel.removeListener('error', onClose);
                    channel.removeListener('close', onClose);
                    if (error || returned) reject(new PaymentBrokerUnavailable());
                    else resolve();
                };
                channel.once('return', onReturn);
                channel.once('error', onClose);
                channel.once('close', onClose);
                try {
                    channel.publish(
                        event.exchange,
                        event.routingKey,
                        Buffer.from(JSON.stringify(event.body)),
                        {
                            mandatory: true,
                            persistent: true,
                            contentType: 'application/json',
                            contentEncoding: 'utf-8',
                            messageId: event.id,
                            correlationId: String(event.body.orderId),
                            type: event.routingKey,
                            headers: this.traces.inject(),
                        },
                        (error: unknown) => finish(error ? new PaymentBrokerUnavailable() : undefined),
                    );
                } catch {
                    finish(new PaymentBrokerUnavailable());
                }
            });
            this.logger.log({
                event: 'payments.outbox.confirmed',
                message_id: event.id,
                order_id: event.body.orderId,
                message_type: event.routingKey,
            });
        });
    }

    async disconnect(channel?: Channel): Promise<void> {
        if (channel && this.consumer !== channel) return;
        const connection = this.connection;
        this.connection = undefined;
        this.consumer = undefined;
        this.publisher = undefined;
        await connection?.close().catch(() => undefined);
    }

    async onApplicationShutdown(): Promise<void> {
        this.stopping = true;
        await this.opening?.catch(() => undefined);
        await this.disconnect();
    }
}
