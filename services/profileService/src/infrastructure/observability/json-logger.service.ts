import { Injectable, type LoggerService } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { readLogCorrelation } from './trace-context.service';

const EVENTS: Record<string, string> = {
    'service.started': 'Profile service started.',
    'service.stopped': 'Profile service stopped.',
    'profile.broker.connected': 'Registration consumer connected.',
    'profile.broker.unavailable': 'Registration broker is temporarily unavailable.',
    'profile.event.processed': 'Registration event processed.',
    'profile.event.retry': 'Registration processing scheduled for retry.',
    'profile.event.dead-lettered': 'Registration event sent to the error queue.',
    'profile.delivery.uncertain': 'Registration delivery is unconfirmed; the original remains unacknowledged.',
    'framework.error': 'Framework operation failed.',
    'framework.warning': 'Framework warning.',
    'framework.message': 'Framework diagnostic event.',
};
const CODES = new Set([
    'REGISTRATION_EVENT_INVALID',
    'REGISTRATION_RETRIES_EXHAUSTED',
    'REGISTRATION_PERSISTENCE_REJECTED',
]);
const LEVELS = { DEBUG: 10, INFO: 20, WARN: 30, ERROR: 40 };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

@Injectable()
export class JsonLogger implements LoggerService {
    private readonly instanceId = process.env.INSTANCE_ID ?? randomUUID();

    log(message: unknown): void {
        this.write('INFO', message);
    }
    warn(message: unknown): void {
        this.write('WARN', message);
    }
    error(message: unknown): void {
        this.write('ERROR', message);
    }
    debug(message: unknown): void {
        this.write('DEBUG', message);
    }
    verbose(message: unknown): void {
        this.write('DEBUG', message);
    }
    fatal(message: unknown): void {
        this.write('ERROR', message);
    }

    private write(level: keyof typeof LEVELS, message: unknown): void {
        const input = typeof message === 'object' && message !== null ? (message as Record<string, unknown>) : {};
        const known = typeof input.event === 'string' && Object.hasOwn(EVENTS, input.event);
        const event = known
            ? String(input.event)
            : level === 'ERROR'
              ? 'framework.error'
              : level === 'WARN'
                ? 'framework.warning'
                : 'framework.message';
        const effectiveLevel = known || level === 'ERROR' || level === 'WARN' ? level : 'DEBUG';
        const configured = process.env.LOG_LEVEL ?? 'INFO';
        const threshold = Object.hasOwn(LEVELS, configured) ? LEVELS[configured as keyof typeof LEVELS] : LEVELS.INFO;
        if (LEVELS[effectiveLevel] < threshold) return;
        const metadata: Record<string, unknown> = {};
        for (const key of ['event_id', 'aggregate_id']) {
            if (typeof input[key] === 'string' && UUID.test(input[key])) metadata[key] = input[key];
        }
        if (
            typeof input.attempt === 'number' &&
            Number.isSafeInteger(input.attempt) &&
            input.attempt >= 1 &&
            input.attempt <= 3
        ) {
            metadata.attempt = input.attempt;
        }
        if (typeof input.duplicate === 'boolean') metadata.duplicate = input.duplicate;
        if (typeof input.code === 'string' && CODES.has(input.code)) metadata.code = input.code;
        const output = effectiveLevel === 'ERROR' ? process.stderr : process.stdout;
        if (output.writableLength > 65536) return;
        output.write(
            JSON.stringify({
                timestamp: new Date().toISOString(),
                level: effectiveLevel,
                service_name: 'profile-service',
                service_version: process.env.SERVICE_VERSION ?? '0.0.1',
                environment: process.env.APP_ENV ?? 'development',
                instance_id: this.instanceId,
                event,
                message: EVENTS[event],
                ...readLogCorrelation(),
                ...metadata,
            }) + '\n',
        );
    }
}
