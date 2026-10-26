import { afterEach, describe, expect, it, jest } from '@jest/globals';
import { context } from '@opentelemetry/api';

import { JsonLogger } from './json-logger.service';
import { readLogCorrelation, TraceContextService } from './trace-context.service';

afterEach(() => {
  jest.restoreAllMocks();
});

describe('Auth observability', () => {
  it('writes the required JSON envelope and excludes arbitrary fields and exception details', () => {
    const output = jest.spyOn(process.stdout, 'write').mockReturnValue(true);
    const errors = jest.spyOn(process.stderr, 'write').mockReturnValue(true);
    const logger = new JsonLogger();
    logger.log({
      event: 'http.request.completed',
      http_method: 'POST',
      http_route: '/api/v1/sessions',
      status_code: 200,
      duration_ms: 2.5,
      password: 'SecretPassword!',
      code: '123456',
      accessToken: 'secret-access',
      refreshToken: 'secret-refresh',
      email: 'private@example.com',
      Authorization: 'Bearer secret-access',
      cookies: 'secret-cookie',
      message: 'private\nprovider detail',
      stack_trace: 'private stack',
      body: { password: 'SecretPassword!' },
      url: 'https://signed.example/?secret=1',
    });
    logger.error(new Error('private@example.com SecretPassword! secret-access'));
    logger.debug({ event: 'auth.outbox.delivery.retry', code: 'OUTBOX_UNAVAILABLE' });

    expect(output).toHaveBeenCalledTimes(1);
    expect(errors).toHaveBeenCalledTimes(1);
    const line = String(output.mock.calls[0][0]);
    const row = JSON.parse(line) as Record<string, unknown>;
    expect(row).toMatchObject({
      level: 'INFO',
      service_name: 'auth-service',
      service_version: '0.0.1',
      environment: 'test',
      event: 'http.request.completed',
      message: 'HTTP request completed.',
      trace_id: null,
      span_id: null,
      http_route: '/api/v1/sessions',
      status_code: 200,
    });
    expect(row.timestamp).toEqual(expect.stringMatching(/^\d{4}-\d{2}-\d{2}T.*Z$/));
    expect(typeof row.instance_id).toBe('string');
    expect(line.split('\n')).toHaveLength(2);
    const serialized = JSON.stringify([output.mock.calls, errors.mock.calls]);
    for (const secret of [
      'SecretPassword!',
      '123456',
      'secret-access',
      'secret-refresh',
      'private@example.com',
      'secret-cookie',
      'provider detail',
      'private stack',
      'signed.example',
    ]) {
      expect(serialized).not.toContain(secret);
    }
  });

  it('keeps asynchronous job and producer correlation and starts jobs outside HTTP context', async () => {
    const tracing = new TraceContextService();
    const http = tracing.startHttp(undefined, 'http-request');
    await context.with(http.scope, async () => {
      await tracing.runJob(async () => {
        await Promise.resolve();
        const job = readLogCorrelation();
        expect(job.trace_id).toMatch(/^[0-9a-f]{32}$/);
        expect(job.span_id).toMatch(/^[0-9a-f]{16}$/);
        expect(job.trace_id).not.toBe(http.span.spanContext().traceId);
        expect(job.request_id).toBeUndefined();
        await tracing.runProducer(async (header) => {
          await Promise.resolve();
          const producer = readLogCorrelation();
          expect(producer.trace_id).toBe(job.trace_id);
          expect(producer.span_id).not.toBe(job.span_id);
          expect(header).toBe(`00-${producer.trace_id}-${producer.span_id}-01`);
        });
        expect(readLogCorrelation()).toEqual(job);
      });
    });
    http.span.end();
    expect(readLogCorrelation().trace_id).toBeNull();
  });
});
