import { Injectable, type LoggerService, type OnApplicationShutdown } from '@nestjs/common';
import { SpanStatusCode, trace } from '@opentelemetry/api';
import { randomUUID } from 'node:crypto';

import { readLogCorrelation } from './trace-context.service';

type Level = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';
const LEVEL_PRIORITY: Record<Level, number> = { DEBUG: 10, INFO: 20, WARN: 30, ERROR: 40 };
const DEFAULT_INSTANCE_ID = randomUUID();
const MAX_OUTPUT_BUFFER_BYTES = 65_536;
const EVENT_MESSAGES: Record<string, string> = {
  'service.started': 'Auth service started.',
  'service.stopped': 'Auth service stopped.',
  'service.start.failed': 'Auth service could not start.',
  'http.request.completed': 'HTTP request completed.',
  'auth.outbox.batch.completed': 'Registration outbox batch completed.',
  'auth.outbox.event.blocked': 'Invalid registration event blocked.',
  'auth.outbox.delivery.retry': 'Registration event scheduled for retry.',
  'auth.outbox.poll.failed': 'Registration outbox is temporarily unavailable.',
  'auth.email_confirmation.dispatch.failed': 'Email confirmation dispatch failed.',
  'auth.password_recovery.dispatch.failed': 'Password recovery email dispatch failed.',
  'auth.password_recovery.cleanup.failed': 'Temporary recovery session cleanup failed.',
  'framework.message': 'Framework diagnostic event.',
  'framework.warning': 'Framework warning.',
  'framework.error': 'Framework operation failed.',
};
const LEGACY_EVENTS: Record<string, string> = {
  'Email confirmation dispatch failed.': 'auth.email_confirmation.dispatch.failed',
  'Password recovery email dispatch failed.': 'auth.password_recovery.dispatch.failed',
  'Temporary recovery session cleanup failed.': 'auth.password_recovery.cleanup.failed',
};
const ERROR_CODES = new Set([
  'REGISTRATION_EVENT_INVALID',
  'REGISTRATION_BROKER_UNAVAILABLE',
  'REGISTRATION_PUBLICATION_TIMEOUT',
  'REGISTRATION_PUBLICATION_NACK',
  'REGISTRATION_EVENT_UNROUTABLE',
  'REGISTRATION_PUBLISHER_BUSY',
  'REGISTRATION_PUBLICATION_FAILED',
  'OUTBOX_UNAVAILABLE',
]);
const ERROR_TYPES = new Set(['UnexpectedError', 'HttpException', 'ClientDisconnected']);
const HTTP_METHODS = new Set(['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']);
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function allowedFields(input: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const key of ['published', 'retried', 'blocked', 'attempt', 'status_code', 'duration_ms']) {
    const value = input[key];
    if (typeof value === 'number' && Number.isFinite(value) && value >= 0) result[key] = value;
  }
  for (const key of ['event_id', 'aggregate_id']) {
    const value = input[key];
    if (typeof value === 'string' && UUID_PATTERN.test(value)) result[key] = value;
  }
  if (typeof input.code === 'string' && ERROR_CODES.has(input.code)) result.code = input.code;
  if (Array.isArray(input.codes)) {
    result.codes = input.codes
      .filter((code): code is string => typeof code === 'string' && ERROR_CODES.has(code))
      .slice(0, 8);
  }
  if (typeof input.error_type === 'string' && ERROR_TYPES.has(input.error_type)) {
    result.error_type = input.error_type;
  }
  if (typeof input.http_method === 'string' && HTTP_METHODS.has(input.http_method)) {
    result.http_method = input.http_method;
  }
  if (
    typeof input.http_route === 'string' &&
    /^(?:\/[a-zA-Z0-9/{}:_.-]{0,199}|unmatched)$/.test(input.http_route)
  ) {
    result.http_route = input.http_route;
  }
  return result;
}

@Injectable()
export class JsonLogger implements LoggerService, OnApplicationShutdown {
  private readonly instanceId = process.env.INSTANCE_ID ?? DEFAULT_INSTANCE_ID;
  private started = false;

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

  serviceStarted(): void {
    this.started = true;
    this.log({ event: 'service.started' });
  }

  onApplicationShutdown(): void {
    if (this.started) this.log({ event: 'service.stopped' });
  }

  private write(level: Level, message: unknown): void {
    const input = isRecord(message) ? message : {};
    const requestedEvent =
      typeof input.event === 'string'
        ? input.event
        : typeof message === 'string'
          ? LEGACY_EVENTS[message]
          : undefined;
    const knownEvent =
      requestedEvent !== undefined && Object.hasOwn(EVENT_MESSAGES, requestedEvent);
    const event = knownEvent
      ? requestedEvent
      : level === 'ERROR'
        ? 'framework.error'
        : level === 'WARN'
          ? 'framework.warning'
          : 'framework.message';
    const effectiveLevel = knownEvent || level === 'ERROR' || level === 'WARN' ? level : 'DEBUG';
    const configuredLevel = process.env.LOG_LEVEL ?? 'INFO';
    const threshold = Object.hasOwn(LEVEL_PRIORITY, configuredLevel)
      ? LEVEL_PRIORITY[configuredLevel as Level]
      : LEVEL_PRIORITY.INFO;
    if (LEVEL_PRIORITY[effectiveLevel] < threshold) return;
    if (effectiveLevel === 'ERROR')
      trace.getActiveSpan()?.setStatus({ code: SpanStatusCode.ERROR });

    const record = {
      timestamp: new Date().toISOString(),
      level: effectiveLevel,
      service_name: 'auth-service',
      service_version: process.env.SERVICE_VERSION ?? '0.0.1',
      environment: process.env.APP_ENV ?? 'development',
      instance_id: this.instanceId,
      event,
      message: EVENT_MESSAGES[event],
      ...readLogCorrelation(),
      ...allowedFields(input),
      ...(!knownEvent && effectiveLevel === 'ERROR' ? { error_type: 'UnexpectedError' } : {}),
    };
    const output = effectiveLevel === 'ERROR' ? process.stderr : process.stdout;
    if (output.writableLength > MAX_OUTPUT_BUFFER_BYTES) return;
    output.write(`${JSON.stringify(record)}\n`);
  }
}
