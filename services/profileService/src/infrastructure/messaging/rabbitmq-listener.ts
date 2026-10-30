import { Inject, Injectable, type BeforeApplicationShutdown, type OnApplicationBootstrap } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { readFileSync } from 'node:fs';
import type { ChannelModel, ConfirmChannel, ConsumeMessage } from 'amqplib';
import { UserRegisteredConsumer } from '../../interfaces/messaging/user-registered.consumer';
import { JsonLogger } from '../observability/json-logger.service';
import { TraceContextService } from '../observability/trace-context.service';
import { confirmedHandoff } from './confirmed-handoff';
import { declareProfileTopology, PROFILE_TOPOLOGY as topology } from './rabbitmq-topology';

export const AMQP_CONNECTOR = Symbol('AMQP_CONNECTOR');
export interface AmqpConnector {
    connect(
        uri: string,
        options: { timeout: number; ca?: Buffer[]; rejectUnauthorized: boolean },
    ): Promise<ChannelModel>;
}

async function deadline<T>(work: Promise<T>, milliseconds: number): Promise<T> {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
        return await Promise.race([
            work,
            new Promise<never>((_, reject) => {
                timer = setTimeout(() => reject(new Error('REGISTRATION_BROKER_TIMEOUT')), milliseconds);
            }),
        ]);
    } finally {
        clearTimeout(timer);
    }
}

@Injectable()
export class RabbitMqListener implements OnApplicationBootstrap, BeforeApplicationShutdown {
    private connection?: ChannelModel;
    private channel?: ConfirmChannel;
    private consumerTag?: string;
    private timer?: ReturnType<typeof setTimeout>;
    private active?: Promise<void>;
    private opening?: Promise<void>;
    private connecting = false;
    private stopping = false;
    private connected = false;
    private failures = 0;

    constructor(
        private readonly config: ConfigService,
        @Inject(AMQP_CONNECTOR) private readonly connector: AmqpConnector,
        private readonly consumer: UserRegisteredConsumer,
        private readonly logger: JsonLogger,
        private readonly tracing: TraceContextService,
    ) {}

    get isReady(): boolean {
        return !this.config.get<boolean>('RABBITMQ_CONSUMER_ENABLED', true) || this.connected;
    }

    onApplicationBootstrap(): void {
        if (this.config.get<boolean>('RABBITMQ_CONSUMER_ENABLED', true)) this.schedule(0);
    }

    private schedule(delay?: number): void {
        if (this.stopping || this.timer) return;
        const milliseconds = delay ?? Math.min(30000, 1000 * 2 ** Math.min(this.failures++, 5));
        this.timer = setTimeout(() => {
            this.timer = undefined;
            if (this.stopping || this.connecting) return;
            this.opening = this.open();
            void this.opening;
        }, milliseconds);
        this.timer.unref();
    }

    private async open(): Promise<void> {
        this.connecting = true;
        try {
            const uri = new URL(this.config.getOrThrow<string>('RABBITMQ_URI'));
            uri.searchParams.set('heartbeat', '5');
            const caPath = this.config.get<string>('RABBITMQ_CA_PATH');
            const connection = await this.connector.connect(uri.toString(), {
                timeout: 3000,
                rejectUnauthorized: true,
                ...(caPath ? { ca: [readFileSync(caPath)] } : {}),
            });
            connection.on('error', () => undefined);
            if (this.stopping) {
                await deadline(connection.close(), 1000).catch(() => undefined);
                return;
            }
            this.connection = connection;
            connection.on('close', () => {
                if (this.connection === connection) this.recover();
            });
            const channel = await deadline(connection.createConfirmChannel(), 5000);
            this.channel = channel;
            channel.on('error', () => undefined);
            channel.on('close', () => {
                if (this.channel === channel) this.recover();
            });
            await deadline(
                declareProfileTopology(channel, [
                    this.config.get<number>('RABBITMQ_RETRY_DELAY_1_MS', 5000),
                    this.config.get<number>('RABBITMQ_RETRY_DELAY_2_MS', 30000),
                ]),
                10000,
            );
            await channel.prefetch(1);
            const subscription = await channel.consume(
                topology.queue,
                (message) => {
                    if (!message) {
                        this.recover();
                        return;
                    }
                    const work = this.tracing.runConsumer(message.properties.headers?.traceparent, () =>
                        this.deliver(channel, message),
                    );
                    this.active = work.catch(() => {
                        this.logger.warn({ event: 'profile.delivery.uncertain' });
                        if (this.channel === channel) this.recover();
                    });
                },
                { noAck: false },
            );
            this.consumerTag = subscription.consumerTag;
            if (this.stopping || this.channel !== channel) throw new Error('REGISTRATION_CHANNEL_CLOSED');
            this.connected = true;
            this.failures = 0;
            this.logger.log({ event: 'profile.broker.connected' });
        } catch {
            if (!this.stopping) {
                if (this.failures === 0) this.logger.warn({ event: 'profile.broker.unavailable' });
                else this.logger.debug({ event: 'profile.broker.unavailable' });
            }
            await this.disconnect();
        } finally {
            this.connecting = false;
            if (!this.connected && !this.stopping) this.schedule();
        }
    }

    private deliver(channel: ConfirmChannel, message: ConsumeMessage): Promise<void> {
        return this.consumer.handle(message, {
            ack: () => {
                if (this.channel !== channel) throw new Error('REGISTRATION_CHANNEL_CLOSED');
                channel.ack(message);
            },
            retry: (attempt) =>
                confirmedHandoff(channel, message, topology.retryExchange, topology.retries[attempt - 2].routingKey, {
                    'x-profile-attempt': attempt,
                }),
            deadLetter: (reason) =>
                confirmedHandoff(channel, message, topology.deadLetterExchange, topology.deadLetterRoutingKey, {
                    'x-profile-failure-code': reason,
                }),
        });
    }

    private recover(): void {
        if (this.connected) this.logger.warn({ event: 'profile.broker.unavailable' });
        this.connected = false;
        void this.disconnect().then(() => this.schedule());
    }

    private async disconnect(): Promise<void> {
        const connection = this.connection;
        this.connection = undefined;
        this.channel = undefined;
        this.connected = false;
        this.consumerTag = undefined;
        if (connection) await deadline(connection.close(), 1000).catch(() => undefined);
    }

    async beforeApplicationShutdown(): Promise<void> {
        this.stopping = true;
        clearTimeout(this.timer);
        if (this.channel && this.consumerTag) {
            await deadline(this.channel.cancel(this.consumerTag), 2000).catch(() => undefined);
        }
        if (this.active) await deadline(this.active, 15000).catch(() => undefined);
        await this.disconnect();
        if (this.opening) await deadline(this.opening, 5000).catch(() => undefined);
        this.logger.log({ event: 'service.stopped' });
    }
}
