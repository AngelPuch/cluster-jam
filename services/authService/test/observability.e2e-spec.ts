import { INestApplication } from '@nestjs/common';
import {
  afterAll,
  beforeAll,
  beforeEach,
  afterEach,
  describe,
  expect,
  it,
  jest,
} from '@jest/globals';
import request from 'supertest';
import type { App } from 'supertest/types';

import { AuthLoginError, AuthLoginFailure } from '../src/application/auth/errors/auth-login.error';
import {
  AUTH_PROVIDER_PORT,
  type AuthProviderPort,
} from '../src/application/ports/auth-provider.port';
import { JsonLogger } from '../src/infrastructure/observability/json-logger.service';
import { createTestApp } from './helpers/create-test-app';

function rows(spy: jest.SpiedFunction<typeof process.stdout.write>): Record<string, unknown>[] {
  return spy.mock.calls
    .map(([line]) => String(line))
    .filter((line) => line.startsWith('{'))
    .map((line) => JSON.parse(line) as Record<string, unknown>);
}

describe('Auth structured logs (e2e)', () => {
  let app: INestApplication<App>;
  let login: jest.SpiedFunction<AuthProviderPort['loginUser']>;
  let output: jest.SpiedFunction<typeof process.stdout.write>;
  let errors: jest.SpiedFunction<typeof process.stderr.write>;

  beforeAll(async () => {
    app = await createTestApp();
    app.useLogger(app.get(JsonLogger));
    login = jest.spyOn(app.get<AuthProviderPort>(AUTH_PROVIDER_PORT), 'loginUser');
  });
  beforeEach(() => {
    login.mockReset();
    output = jest.spyOn(process.stdout, 'write').mockReturnValue(true);
    errors = jest.spyOn(process.stderr, 'write').mockReturnValue(true);
  });
  afterEach(() => {
    output.mockRestore();
    errors.mockRestore();
  });
  afterAll(async () => {
    login.mockRestore();
    await app.close();
  });

  it('logs one result for each concurrent request without logging credentials or session tokens', async () => {
    login.mockImplementation(async (input) => {
      await Promise.resolve();
      if (input.password === 'RejectedPassword!') {
        throw new AuthLoginError(AuthLoginFailure.InvalidCredentials);
      }
      return {
        userId: '11111111-1111-4111-8111-111111111111',
        email: input.email,
        accessToken: 'secret-access-token',
        refreshToken: 'secret-refresh-token',
        expiresIn: 900,
        tokenType: 'bearer',
      };
    });
    const traceId = '4bf92f3577b34da6a3ce929d0e0e4736';
    const [success, denied] = await Promise.all([
      request(app.getHttpServer())
        .post('/api/v1/sessions?otp=123456')
        .set('traceparent', `00-${traceId}-00f067aa0ba902b7-01`)
        .set('Authorization', 'Bearer private-header')
        .set('Cookie', 'private-cookie')
        .send({ email: 'private@example.com', password: 'SecretPassword!' })
        .expect(200),
      request(app.getHttpServer())
        .post('/api/v1/sessions')
        .send({ email: 'other@example.com', password: 'RejectedPassword!' })
        .expect(401),
    ]);
    const entries = rows(output);
    expect(entries).toHaveLength(2);
    expect(rows(errors)).toHaveLength(0);
    const completed = entries.find((row) => row.status_code === 200);
    expect(completed).toMatchObject({
      level: 'INFO',
      event: 'http.request.completed',
      trace_id: traceId,
      http_route: '/api/v1/sessions',
      http_method: 'POST',
      request_id: success.headers['x-request-id'],
    });
    const rejected = entries.find((row) => row.status_code === 401);
    expect(rejected?.request_id).toBe(denied.headers['x-request-id']);
    expect(rejected?.trace_id).not.toBe(traceId);
    expect(completed?.span_id).not.toBe('00f067aa0ba902b7');
    const serialized = JSON.stringify([output.mock.calls, errors.mock.calls]);
    for (const secret of [
      'private@example.com',
      'other@example.com',
      'SecretPassword!',
      'RejectedPassword!',
      '123456',
      'secret-access-token',
      'secret-refresh-token',
      'private-header',
      'private-cookie',
    ])
      expect(serialized).not.toContain(secret);
  });

  it('logs unexpected failures once and correlates their sanitized problem response', async () => {
    login.mockRejectedValue(new Error('private@example.com SecretPassword! private stack'));
    const response = await request(app.getHttpServer())
      .post('/api/v1/sessions')
      .send({ email: 'private@example.com', password: 'SecretPassword!' })
      .expect(500);
    const entries = rows(errors);
    expect(entries).toHaveLength(1);
    expect(output).not.toHaveBeenCalled();
    const problem = response.body as { traceId: string };
    expect(entries[0]).toMatchObject({
      level: 'ERROR',
      event: 'http.request.completed',
      error_type: 'UnexpectedError',
      status_code: 500,
      trace_id: problem.traceId,
    });
    expect(problem.traceId).toMatch(/^[0-9a-f]{32}$/);
    expect(JSON.stringify(entries)).not.toMatch(/private@example|SecretPassword|private stack/);
  });

  it('ignores probes, replaces invalid trace context and keeps unknown paths and malformed JSON out of logs', async () => {
    await request(app.getHttpServer()).get('/health/live').expect(200);
    expect(output).not.toHaveBeenCalled();
    const response = await request(app.getHttpServer())
      .get('/api/v1/private@example.com?otp=123456')
      .set('traceparent', '00-00000000000000000000000000000000-0000000000000000-01')
      .expect(404);
    await request(app.getHttpServer())
      .post('/api/v1/sessions')
      .set('Content-Type', 'application/json')
      .send('{"password":"SecretPassword!"')
      .expect(400);
    const entries = rows(output);
    expect(entries).toHaveLength(2);
    const problem = response.body as { traceId: string };
    expect(entries[0]).toMatchObject({
      http_route: 'unmatched',
      status_code: 404,
      trace_id: problem.traceId,
      level: 'INFO',
    });
    expect(problem.traceId).not.toBe('00000000000000000000000000000000');
    expect(problem.traceId).toMatch(/^[0-9a-f]{32}$/);
    expect(rows(errors)).toHaveLength(0);
    expect(JSON.stringify(entries)).not.toMatch(/private@example|123456|SecretPassword/);
  });
});
