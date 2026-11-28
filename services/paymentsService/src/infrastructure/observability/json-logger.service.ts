import { Injectable, type LoggerService } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { readLogCorrelation } from './trace-context.service';
import { PaymentMessageType } from '../../application/payments/payment-messages';

const EVENTS: Record<string, string> = {
    'payments.migrations.applied': 'Payments migrations applied.',
    'payments.migrations.failed': 'Payments migrations could not be applied.',
    'service.started': 'Payments service started.',
    'service.failed': 'Payments service could not start.',
    'http.request.completed': 'HTTP request completed.',
    'payments.broker.connected': 'Payments broker connected.',
    'payments.consumer.paused': 'Command consumer is paused until a Stripe test key is configured.',
    'payments.messaging.unavailable': 'Payments messaging will retry on the next cycle.',
    'payments.command.committed': 'Payment command committed before acknowledgement.',
    'payments.command.rejected': 'Payment command rejected to the broker dead-letter queue.',
    'payments.outbox.confirmed': 'Payment event received a routed broker confirmation.',
    'payments.webhook.processed': 'Verified Stripe payment notification processed.',
    'payments.refund.unresolved': 'Stripe refund requires review of the original financial operation.',
    'framework.error': 'Framework operation failed.',
    'framework.warning': 'Framework warning.',
    'framework.message': 'Framework diagnostic event.',
};
const LEVELS = { DEBUG: 10, INFO: 20, WARN: 30, ERROR: 40 };
const INSTANCE_ID = randomUUID();
const MESSAGE_TYPES: ReadonlySet<string> = new Set(Object.values(PaymentMessageType));
const REASONS = new Set([
    'INVALID_COMMAND',
    'RETRIES_EXHAUSTED',
    'PAYMENT_COMMAND_CONFLICT',
    'PAYMENT_PROVIDER_MISMATCH',
    'PAYMENT_RECOVERY_REQUIRED',
]);

@Injectable()
export class JsonLogger implements LoggerService {
    log(value: unknown): void {
        this.write('INFO', value);
    }
    warn(value: unknown): void {
        this.write('WARN', value);
    }
    error(value: unknown): void {
        this.write('ERROR', value);
    }
    debug(value: unknown): void {
        this.write('DEBUG', value);
    }
    verbose(value: unknown): void {
        this.write('DEBUG', value);
    }

    private write(level: keyof typeof LEVELS, value: unknown): void {
        const input = typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
        const known = typeof input.event === 'string' && Object.hasOwn(EVENTS, input.event);
        const event = known
            ? String(input.event)
            : level === 'ERROR'
              ? 'framework.error'
              : level === 'WARN'
                ? 'framework.warning'
                : 'framework.message';
        const effective = known || level === 'ERROR' || level === 'WARN' ? level : 'DEBUG';
        const configured = process.env.LOG_LEVEL ?? 'INFO';
        const threshold = LEVELS[configured as keyof typeof LEVELS] ?? LEVELS.INFO;
        if (LEVELS[effective] < threshold) return;
        const metadata: Record<string, number | string> = {};
        if (Number.isInteger(input.status_code) && Number(input.status_code) >= 100 && Number(input.status_code) <= 599)
            metadata.status_code = Number(input.status_code);
        if (Number.isSafeInteger(input.duration_ms) && Number(input.duration_ms) >= 0)
            metadata.duration_ms = Number(input.duration_ms);
        for (const key of ['order_id', 'message_id']) {
            const value = input[key];
            if (
                typeof value === 'string' &&
                /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
            ) {
                metadata[key] = value;
            }
        }
        if (typeof input.message_type === 'string' && MESSAGE_TYPES.has(input.message_type))
            metadata.message_type = input.message_type;
        if (typeof input.reason === 'string' && REASONS.has(input.reason)) metadata.reason = input.reason;
        if (typeof input.stripe_event_id === 'string' && /^evt_[A-Za-z0-9]{1,200}$/.test(input.stripe_event_id)) {
            metadata.stripe_event_id = input.stripe_event_id;
        }
        const output = effective === 'ERROR' ? process.stderr : process.stdout;
        if (output.writableLength > 65536) return;
        output.write(
            JSON.stringify({
                timestamp: new Date().toISOString(),
                level: effective,
                service_name: 'payments-service',
                service_version: process.env.SERVICE_VERSION ?? '0.0.1',
                environment: process.env.APP_ENV ?? 'development',
                instance_id: process.env.INSTANCE_ID ?? INSTANCE_ID,
                event,
                message: EVENTS[event],
                ...readLogCorrelation(),
                ...metadata,
            }) + '\n',
        );
    }
}
