import { INestApplication, Logger } from '@nestjs/common';
import {
    afterAll,
    afterEach,
    beforeAll,
    beforeEach,
    describe,
    expect,
    it,
    jest,
} from '@jest/globals';
import { type OpenAPIObject } from '@nestjs/swagger';
import request from 'supertest';
import { App } from 'supertest/types';

import { PASSWORD_RECOVERY_MESSAGE } from '../src/interfaces/http/auth/dto/password-recovery-request-response.dto';
import { createTestApp } from './helpers/create-test-app';
import { type ProblemResponse } from './helpers/problem-response';

const requestPath = '/api/v1/password-recovery-requests';
const recoveryPath = '/api/v1/password-recoveries';
const input = {
    email: 'user@example.com',
    code: '012345',
    newPassword: 'NewStrongPassword123!',
};
const user = { id: '11111111-1111-4111-8111-111111111111' };
const verifiedSession = {
    access_token: 'private-access-token',
    refresh_token: 'private-refresh-token',
    user,
};

describe('Password recovery API (e2e)', () => {
    let app: INestApplication<App>;
    let fetchSpy: jest.SpiedFunction<typeof fetch>;

    beforeAll(async () => {
        app = await createTestApp();
    });

    beforeEach(() => {
        fetchSpy = jest.spyOn(globalThis, 'fetch');
        jest.spyOn(Logger.prototype, 'warn').mockImplementation(() => {});
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    afterAll(async () => {
        await app.close();
    });

    it('returns identical results for existing and unknown emails', async () => {
        fetchSpy.mockResolvedValue(jsonResponse(200, {}));
        const existing = await request(app.getHttpServer())
            .post(requestPath)
            .send({ email: 'user@example.com' })
            .expect(200)
            .expect('Cache-Control', 'no-store');
        const unknown = await request(app.getHttpServer())
            .post(requestPath)
            .send({ email: 'unknown@example.com' })
            .expect(200);
        expect(existing.body).toEqual({ message: PASSWORD_RECOVERY_MESSAGE });
        expect(unknown.body).toEqual(existing.body);
    });

    it.each([429, 500])('keeps dispatch status %s neutral', async (status) => {
        fetchSpy.mockResolvedValue(
            jsonResponse(status, { msg: 'private email details' }),
        );
        const response = await request(app.getHttpServer())
            .post(requestPath)
            .send({ email: 'user@example.com' })
            .expect(200);
        expect(response.body).toEqual({ message: PASSWORD_RECOVERY_MESSAGE });
    });

    it('keeps dispatch transport errors neutral', async () => {
        fetchSpy.mockRejectedValue(new Error('private email details'));
        const response = await request(app.getHttpServer())
            .post(requestPath)
            .send({ email: 'user@example.com' })
            .expect(200);
        expect(response.body).toEqual({ message: PASSWORD_RECOVERY_MESSAGE });
    });

    it.each([
        { email: 'invalid' },
        {
            email: 'user@example.com',
            redirectTo: 'https://untrusted.example.com',
        },
        { email: 'user@example.com', userId: user.id },
    ])('rejects invalid recovery request fields', async (body) => {
        const response = await request(app.getHttpServer())
            .post(requestPath)
            .send(body)
            .expect(422)
            .expect('Content-Type', /application\/problem\+json/);
        expect((response.body as ProblemResponse).code).toBe(
            'VALIDATION_ERROR',
        );
        expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('completes recovery without exposing a session or requiring login', async () => {
        fetchSpy
            .mockResolvedValueOnce(jsonResponse(200, verifiedSession))
            .mockResolvedValueOnce(jsonResponse(200, user))
            .mockResolvedValueOnce(new Response(null, { status: 204 }));
        const response = await request(app.getHttpServer())
            .post(recoveryPath)
            .send(input)
            .expect(204)
            .expect('Cache-Control', 'no-store');
        expect(response.text).toBe('');
        expect(response.headers['set-cookie']).toBeUndefined();
        expect(fetchSpy.mock.calls[0][1]?.body).toBe(
            JSON.stringify({
                email: input.email,
                token: input.code,
                type: 'recovery',
            }),
        );
        expect(fetchSpy.mock.calls[1][1]?.body).toBe(
            JSON.stringify({ password: input.newPassword }),
        );
    });

    it.each([
        {},
        { ...input, email: 'invalid' },
        { code: '012345', newPassword: 'NewStrongPassword123!' },
        { email: 'user@example.com', newPassword: 'NewStrongPassword123!' },
        { ...input, code: '' },
        { ...input, code: '12345' },
        { ...input, code: '1234567' },
        { ...input, code: '12A456' },
        { ...input, code: '12 456' },
        { ...input, code: 123456 },
        { ...input, newPassword: 'short' },
        { ...input, type: 'email' },
        { ...input, tokenHash: 'obsolete-hash' },
        { ...input, userId: user.id },
        { ...input, role: 'administrator' },
    ])(
        'rejects invalid completion fields before consuming the code',
        async (body) => {
            const response = await request(app.getHttpServer())
                .post(recoveryPath)
                .send(body)
                .expect(422)
                .expect('Content-Type', /application\/problem\+json/);
            expect((response.body as ProblemResponse).code).toBe(
                'VALIDATION_ERROR',
            );
            expect(fetchSpy).not.toHaveBeenCalled();
        },
    );

    it('does not accept a login Bearer token instead of recovery proof', async () => {
        const response = await request(app.getHttpServer())
            .post(recoveryPath)
            .set('Authorization', 'Bearer login-access-token')
            .send({ newPassword: 'NewStrongPassword123!' })
            .expect(422);
        expect((response.body as ProblemResponse).code).toBe(
            'VALIDATION_ERROR',
        );
        expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('returns a sanitized 401 for expired or reused recovery proof', async () => {
        fetchSpy.mockResolvedValue(
            jsonResponse(403, {
                error_code: 'otp_expired',
                msg: 'private-token',
            }),
        );
        const response = await request(app.getHttpServer())
            .post(recoveryPath)
            .send(input)
            .expect(401)
            .expect('Content-Type', /application\/problem\+json/);
        expect(response.body).toEqual({
            type: 'about:blank',
            title: 'Unauthorized',
            status: 401,
            detail: 'The recovery code is invalid, expired or already used.',
            instance: recoveryPath,
            code: 'INVALID_RECOVERY_CODE',
        });
        expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    it('binds the code to its email and rejects reuse after success', async () => {
        let consumed = false;
        fetchSpy.mockImplementation((url, options) => {
            const body =
                typeof options?.body === 'string'
                    ? (JSON.parse(options.body) as Record<string, string>)
                    : {};
            const target =
                typeof url === 'string'
                    ? url
                    : url instanceof URL
                      ? url.href
                      : url.url;
            if (target.endsWith('/verify')) {
                if (
                    consumed ||
                    body.email !== input.email ||
                    body.token !== input.code ||
                    body.type !== 'recovery'
                ) {
                    return Promise.resolve(
                        jsonResponse(403, { error_code: 'otp_expired' }),
                    );
                }
                consumed = true;
                return Promise.resolve(jsonResponse(200, verifiedSession));
            }
            if (target.endsWith('/user')) {
                return Promise.resolve(jsonResponse(200, user));
            }
            return Promise.resolve(new Response(null, { status: 204 }));
        });

        await request(app.getHttpServer())
            .post(recoveryPath)
            .send({ ...input, email: 'someone@example.com' })
            .expect(401);
        expect(consumed).toBe(false);
        await request(app.getHttpServer())
            .post(recoveryPath)
            .send(input)
            .expect(204);
        const reused = await request(app.getHttpServer())
            .post(recoveryPath)
            .send(input)
            .expect(401);
        expect((reused.body as ProblemResponse).code).toBe(
            'INVALID_RECOVERY_CODE',
        );
        expect(
            fetchSpy.mock.calls.filter(
                ([url]) => typeof url === 'string' && url.endsWith('/user'),
            ),
        ).toHaveLength(1);
    });

    it.each([
        [422, 'weak_password', 422, 'WEAK_PASSWORD'],
        [422, 'same_password', 409, 'SAME_PASSWORD'],
        [403, 'insufficient_aal', 403, 'PASSWORD_RECOVERY_NOT_ALLOWED'],
        [422, 'validation_failed', 422, 'INVALID_REQUEST'],
        [401, 'session_not_found', 401, 'INVALID_RECOVERY_CODE'],
        [429, 'over_request_rate_limit', 429, 'TOO_MANY_REQUESTS'],
        [503, 'unexpected_failure', 503, 'SERVICE_UNAVAILABLE'],
    ] as const)(
        'maps update %s/%s to HTTP %s/%s',
        async (providerStatus, code, status, expectedCode) => {
            fetchSpy
                .mockResolvedValueOnce(jsonResponse(200, verifiedSession))
                .mockResolvedValueOnce(
                    jsonResponse(providerStatus, {
                        code,
                        msg: 'private-password',
                    }),
                )
                .mockResolvedValueOnce(new Response(null, { status: 204 }));
            const response = await request(app.getHttpServer())
                .post(recoveryPath)
                .send(input)
                .expect(status)
                .expect('Content-Type', /application\/problem\+json/);
            expect((response.body as ProblemResponse).code).toBe(expectedCode);
            expect(JSON.stringify(response.body)).not.toContain(
                'private-password',
            );
            expect(JSON.stringify(response.body)).not.toContain(
                'private-access-token',
            );
        },
    );

    it('maps a verification transport failure to sanitized 503', async () => {
        fetchSpy.mockRejectedValue(new Error('private-network-details'));
        const response = await request(app.getHttpServer())
            .post(recoveryPath)
            .send(input)
            .expect(503)
            .expect('Content-Type', /application\/problem\+json/);
        expect((response.body as ProblemResponse).code).toBe(
            'SERVICE_UNAVAILABLE',
        );
        expect(JSON.stringify(response.body)).not.toContain(
            'private-network-details',
        );
    });

    it('publishes both routes, write-only proof, and actual Problem Details media types', async () => {
        const response = await request(app.getHttpServer())
            .get('/openapi.json')
            .expect(200);
        const document = response.body as OpenAPIObject;
        const requestOperation = document.paths[requestPath]?.post;
        const recoveryOperation = document.paths[recoveryPath]?.post;
        expect(requestOperation?.responses['200']).toBeDefined();
        expect(recoveryOperation?.responses['204']).toBeDefined();
        expect(recoveryOperation?.security ?? []).toEqual([]);
        const unauthorized = recoveryOperation?.responses['401'];
        expect(
            unauthorized && 'content' in unauthorized
                ? unauthorized.content
                : undefined,
        ).toHaveProperty('application/problem+json');
        const schema = document.components?.schemas?.RecoverPasswordDto;
        expect(
            schema && 'properties' in schema
                ? schema.properties?.code
                : undefined,
        ).toMatchObject({ writeOnly: true });
        expect(fetchSpy).not.toHaveBeenCalled();
    });
});

function jsonResponse(status: number, body: unknown): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}
