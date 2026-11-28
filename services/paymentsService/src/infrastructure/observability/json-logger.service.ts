import { Injectable, type LoggerService } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { readLogCorrelation } from './trace-context.service';

const EVENTS: Record<string, string> = {
    'payments.migrations.applied': 'Payments migrations applied.',
    'payments.migrations.failed': 'Payments migrations could not be applied.',
    'service.started': 'Payments service started.',
    'service.failed': 'Payments service could not start.',
    'http.request.completed': 'HTTP request completed.',
    'framework.error': 'Framework operation failed.',
    'framework.warning': 'Framework warning.',
    'framework.message': 'Framework diagnostic event.',
};
const LEVELS = { DEBUG: 10, INFO: 20, WARN: 30, ERROR: 40 };
const INSTANCE_ID = randomUUID();

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
        const metadata: Record<string, number> = {};
        if (Number.isInteger(input.status_code) && Number(input.status_code) >= 100 && Number(input.status_code) <= 599)
            metadata.status_code = Number(input.status_code);
        if (Number.isSafeInteger(input.duration_ms) && Number(input.duration_ms) >= 0)
            metadata.duration_ms = Number(input.duration_ms);
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
