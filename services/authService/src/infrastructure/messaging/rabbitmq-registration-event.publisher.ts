import { Inject, Injectable, OnApplicationShutdown } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { type ChannelModel, type ConfirmChannel, type Message } from 'amqplib';

import {
    REGISTRATION_EXCHANGE,
    REGISTRATION_ROUTING_KEY,
    RegistrationPublicationError,
    type RegistrationEvent,
} from '../../application/events/registration-event';
import type { RegistrationEventPublisherPort } from '../../application/ports/registration-event-publisher.port';

export const AMQP_CONNECTOR = Symbol('AMQP_CONNECTOR');
export interface AmqpConnector {
    connect(url: string, options: { timeout: number }): Promise<ChannelModel>;
}

function withTimeout<T>(work: Promise<T>, milliseconds: number): Promise<T> {
    return new Promise<T>((resolve, reject) => {
        const timer = setTimeout(
            () =>
                reject(
                    new RegistrationPublicationError(
                        'REGISTRATION_PUBLICATION_TIMEOUT',
                    ),
                ),
            milliseconds,
        );
        work.then(resolve, reject)
            .finally(() => clearTimeout(timer))
            .catch(() => undefined);
    });
}

@Injectable()
export class RabbitMqRegistrationEventPublisher
    implements RegistrationEventPublisherPort, OnApplicationShutdown
{
    private connection?: ChannelModel;
    private channel?: ConfirmChannel;
    private publishing = false;

    constructor(
        private readonly config: ConfigService,
        @Inject(AMQP_CONNECTOR) private readonly connector: AmqpConnector,
    ) {}

    async publish(
        event: RegistrationEvent,
        traceparent: string,
    ): Promise<void> {
        if (this.publishing)
            throw new RegistrationPublicationError(
                'REGISTRATION_PUBLISHER_BUSY',
            );
        this.publishing = true;
        try {
            await withTimeout(this.send(event, traceparent), 8_000);
        } catch (error) {
            await this.disconnect();
            if (error instanceof RegistrationPublicationError) throw error;
            throw new RegistrationPublicationError(
                'REGISTRATION_BROKER_UNAVAILABLE',
            );
        } finally {
            this.publishing = false;
        }
    }

    private async getChannel(): Promise<ConfirmChannel> {
        if (this.channel) return this.channel;
        if (this.connection) await this.disconnect();
        const url = new URL(this.config.getOrThrow<string>('RABBITMQ_URL'));
        url.searchParams.set('heartbeat', '5');
        const connection = await this.connector.connect(url.toString(), {
            timeout: 3_000,
        });
        this.connection = connection;
        connection.on('error', () => undefined);
        connection.on('close', () => {
            if (this.connection === connection) {
                this.connection = undefined;
                this.channel = undefined;
            }
        });
        const channel = await connection.createConfirmChannel();
        channel.on('error', () => undefined);
        channel.on('close', () => {
            if (this.channel === channel) this.channel = undefined;
        });
        await channel.assertExchange(REGISTRATION_EXCHANGE, 'topic', {
            durable: true,
        });
        this.channel = channel;
        return channel;
    }

    private async send(
        event: RegistrationEvent,
        traceparent: string,
    ): Promise<void> {
        const channel = await this.getChannel();
        await new Promise<void>((resolve, reject) => {
            let returned = false;
            const cleanup = (): void => {
                channel.off('return', onReturn);
                channel.off('close', onClose);
            };
            const onReturn = (message: Message): void => {
                if (message.properties.messageId === event.eventId)
                    returned = true;
            };
            const onClose = (): void => {
                cleanup();
                reject(
                    new RegistrationPublicationError(
                        'REGISTRATION_CHANNEL_CLOSED',
                    ),
                );
            };
            channel.on('return', onReturn);
            channel.once('close', onClose);
            try {
                channel.publish(
                    REGISTRATION_EXCHANGE,
                    REGISTRATION_ROUTING_KEY,
                    Buffer.from(JSON.stringify(event)),
                    {
                        persistent: true,
                        mandatory: true,
                        contentType: 'application/json',
                        contentEncoding: 'utf-8',
                        messageId: event.eventId,
                        type: event.eventType,
                        appId: 'auth-service',
                        timestamp: Math.floor(
                            Date.parse(event.occurredAt) / 1_000,
                        ),
                        headers: {
                            schemaVersion: event.schemaVersion,
                            traceparent,
                        },
                    },
                    (error: unknown) => {
                        cleanup();
                        if (error)
                            reject(
                                new RegistrationPublicationError(
                                    'REGISTRATION_PUBLICATION_NACK',
                                ),
                            );
                        else if (returned)
                            reject(
                                new RegistrationPublicationError(
                                    'REGISTRATION_EVENT_UNROUTABLE',
                                ),
                            );
                        else resolve();
                    },
                );
            } catch (error) {
                cleanup();
                reject(
                    error instanceof Error
                        ? error
                        : new Error('Publication failed.'),
                );
            }
        });
    }

    private async disconnect(): Promise<void> {
        const connection = this.connection;
        this.connection = undefined;
        this.channel = undefined;
        if (connection) {
            try {
                await withTimeout(connection.close(), 1_000);
            } catch {
                /* Discard. */
            }
        }
    }

    async onApplicationShutdown(): Promise<void> {
        await this.disconnect();
    }
}
