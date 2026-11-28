import { Injectable, type OnApplicationBootstrap, type BeforeApplicationShutdown } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { Channel } from 'amqplib';
import { PublishOutboxService } from '../../application/outbox/publish-outbox.service';
import { PaymentBroker } from '../../infrastructure/messaging/payment-broker';
import { JsonLogger } from '../../infrastructure/observability/json-logger.service';
import { PaymentCommandConsumer } from '../messaging/payment-command.consumer';

@Injectable()
export class PaymentsMessagingWorker implements OnApplicationBootstrap, BeforeApplicationShutdown {
    private timer?: ReturnType<typeof setInterval>;
    private running?: Promise<void>;
    private delivery?: Promise<void>;
    private channel?: Channel;
    private consumerTag?: string;
    private stopping = false;

    constructor(
        private readonly config: ConfigService,
        private readonly broker: PaymentBroker,
        private readonly consumer: PaymentCommandConsumer,
        private readonly outbox: PublishOutboxService,
        private readonly logger: JsonLogger,
    ) {}

    onApplicationBootstrap(): void {
        if (!this.config.get<boolean>('RABBITMQ_ENABLED')) return;
        if (!this.config.get<string>('STRIPE_SECRET_KEY')) this.logger.warn({ event: 'payments.consumer.paused' });
        this.timer = setInterval(() => {
            void this.tick();
        }, 5000);
        void this.tick();
    }

    async tick(): Promise<void> {
        if (this.stopping || !this.config.get<boolean>('RABBITMQ_ENABLED')) return;
        this.running ??= this.run()
            .catch(() => {
                this.logger.warn({ event: 'payments.messaging.unavailable' });
            })
            .finally(() => {
                this.running = undefined;
            });
        await this.running;
    }

    private async run(): Promise<void> {
        const channel = await this.broker.open();
        if (this.stopping) return;
        if (this.config.get<string>('STRIPE_SECRET_KEY') && this.channel !== channel) {
            const registration = await channel.consume(
                'payments.commands.v1',
                (message) => {
                    if (!message) {
                        if (!this.stopping) void this.broker.disconnect(channel);
                        return;
                    }
                    this.delivery = this.consumer.receive(message, channel).catch(async () => {
                        // A lost channel leaves the unacknowledged delivery for replay.
                        this.logger.warn({ event: 'payments.messaging.unavailable' });
                        await this.broker.disconnect(channel);
                    });
                },
                { noAck: false },
            );
            this.channel = channel;
            this.consumerTag = registration.consumerTag;
        }
        await this.outbox.runBatch();
    }

    async beforeApplicationShutdown(): Promise<void> {
        this.stopping = true;
        clearInterval(this.timer);
        await this.running;
        if (this.channel && this.consumerTag) await this.channel.cancel(this.consumerTag).catch(() => undefined);
        await this.delivery;
    }
}
