import { Inject, Injectable } from '@nestjs/common';
import type { Channel, ConsumeMessage } from 'amqplib';
import { setTimeout as delay } from 'node:timers/promises';
import { EnablePaymentService } from '../../application/payments/enable-payment.service';
import { CancelPaymentService } from '../../application/payments/cancel-payment.service';
import {
    PaymentCommandConflict,
    PaymentProviderMismatch,
    PaymentRecoveryRequired,
} from '../../application/payments/payment.error';
import { JsonLogger } from '../../infrastructure/observability/json-logger.service';
import { TraceContextService } from '../../infrastructure/observability/trace-context.service';
import { InvalidPaymentCommand, parsePaymentCommand, PaymentMessageType } from './payment-messages.dto';

@Injectable()
export class PaymentCommandConsumer {
    constructor(
        @Inject(EnablePaymentService) private readonly handler: Pick<EnablePaymentService, 'execute'>,
        private readonly logger: JsonLogger,
        private readonly traces: TraceContextService,
        @Inject(CancelPaymentService) private readonly cancellation: Pick<CancelPaymentService, 'execute'>,
    ) {}

    async receive(message: ConsumeMessage, channel: Channel): Promise<void> {
        await this.traces.runConsumer(message.properties.headers?.traceparent, async () => {
            let command;
            try {
                if (
                    message.content.length > 65536 ||
                    message.properties.contentType !== 'application/json' ||
                    message.properties.deliveryMode !== 2
                )
                    throw new InvalidPaymentCommand();
                command = parsePaymentCommand(JSON.parse(message.content.toString('utf8')) as unknown);
                const messageId: unknown = message.properties.messageId;
                const orderId: unknown = message.properties.correlationId;
                if (
                    message.fields.exchange !== 'payments.commands' ||
                    message.fields.routingKey !== String(command.type) ||
                    typeof messageId !== 'string' ||
                    messageId.toLowerCase() !== command.messageId.toLowerCase() ||
                    typeof orderId !== 'string' ||
                    orderId.toLowerCase() !== command.orderId.toLowerCase() ||
                    message.properties.type !== String(command.type) ||
                    command.type === PaymentMessageType.Refund
                ) {
                    throw new InvalidPaymentCommand();
                }
            } catch {
                channel.reject(message, false);
                this.logger.warn({ event: 'payments.command.rejected', reason: 'INVALID_COMMAND' });
                return;
            }
            const metadata = { message_id: command.messageId, order_id: command.orderId, message_type: command.type };
            for (let attempt = 1; attempt <= 3; attempt++) {
                try {
                    if (command.type === PaymentMessageType.Enable) await this.handler.execute(command);
                    else await this.cancellation.execute(command);
                } catch (error) {
                    const permanent =
                        error instanceof PaymentCommandConflict ||
                        error instanceof PaymentProviderMismatch ||
                        error instanceof PaymentRecoveryRequired;
                    if (permanent || attempt === 3) {
                        channel.reject(message, false);
                        this.logger.warn({
                            event: 'payments.command.rejected',
                            ...metadata,
                            reason: permanent ? error.message : 'RETRIES_EXHAUSTED',
                        });
                        return;
                    }
                    await delay(1000);
                    continue;
                }
                // execute has committed its inbox, financial result and outbox.
                channel.ack(message);
                this.logger.log({ event: 'payments.command.committed', ...metadata });
                return;
            }
        });
    }
}
