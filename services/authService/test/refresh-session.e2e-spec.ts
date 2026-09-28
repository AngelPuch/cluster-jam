import { INestApplication } from '@nestjs/common';
import {
    beforeAll,
    afterAll,
    beforeEach,
    describe,
    expect,
    it,
    jest,
} from '@jest/globals';
import { Test, TestingModule } from '@nestjs/testing';
import { OpenAPIObject } from '@nestjs/swagger';
import request from 'supertest';
import { App } from 'supertest/types';

import {
    AuthRefreshError,
    AuthRefreshFailure,
} from '../src/application/auth/errors/auth-refresh.error';
import {
    AUTH_PROVIDER_PORT,
    type AuthProviderPort,
} from '../src/application/ports/auth-provider.port';
import { AppModule } from '../src/app.module';
import { configureHttpApplication } from '../src/interfaces/http/http.setup';

describe('Session renewal API (e2e)', () => {
    let app: INestApplication<App>;
    let refreshSpy: jest.SpiedFunction<AuthProviderPort['refreshSession']>;

    beforeAll(async () => {
        const moduleFixture: TestingModule = await Test.createTestingModule({
            imports: [AppModule],
        }).compile();

        app = moduleFixture.createNestApplication();
        configureHttpApplication(app);
        await app.init();

        const provider = app.get<AuthProviderPort>(AUTH_PROVIDER_PORT);
        refreshSpy = jest.spyOn(provider, 'refreshSession');
    });

    beforeEach(() => {
        refreshSpy.mockReset();
    });

    it('returns the new session without caching it', async () => {
        refreshSpy.mockResolvedValue({
            userId: '11111111-1111-4111-8111-111111111111',
            email: 'user@example.com',
            accessToken: 'new-access-token',
            refreshToken: 'new-refresh-token',
            expiresIn: 3600,
            tokenType: 'bearer',
        });

        const response = await request(app.getHttpServer())
            .post('/api/v1/session-renewals')
            .send({ refreshToken: 'old-refresh-token' })
            .expect(200);

        expect(response.headers['cache-control']).toBe('no-store');
        expect(response.body).toEqual({
            userId: '11111111-1111-4111-8111-111111111111',
            email: 'user@example.com',
            accessToken: 'new-access-token',
            refreshToken: 'new-refresh-token',
            expiresIn: 3600,
            tokenType: 'bearer',
        });

        expect(refreshSpy).toHaveBeenCalledWith({
            refreshToken: 'old-refresh-token',
        });
    });

    it('rejects missing fields and unexpected properties', async () => {
        const response = await request(app.getHttpServer())
            .post('/api/v1/session-renewals')
            .send({ role: 'administrator' })
            .expect(422)
            .expect('Content-Type', /application\/problem\+json/);

        expect(response.body).toMatchObject({
            status: 422,
            code: 'VALIDATION_ERROR',
        });
        expect(refreshSpy).not.toHaveBeenCalled();
    });

    it('returns 401 for an invalid refresh token', async () => {
        refreshSpy.mockRejectedValue(
            new AuthRefreshError(AuthRefreshFailure.InvalidRefreshToken),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/session-renewals')
            .send({ refreshToken: 'invalid-token' })
            .expect(401)
            .expect('Content-Type', /application\/problem\+json/);

        expect(response.body).toMatchObject({
            status: 401,
            instance: '/api/v1/session-renewals',
            code: 'INVALID_REFRESH_TOKEN',
        });
        expect(JSON.stringify(response.body)).not.toContain('invalid-token');
    });

    it('returns 422 when Supabase rejects renewal data', async () => {
        refreshSpy.mockRejectedValue(
            new AuthRefreshError(AuthRefreshFailure.InvalidRequest),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/session-renewals')
            .send({ refreshToken: 'token' })
            .expect(422);

        const body = response.body as { code: string };
        expect(body.code).toBe('INVALID_REQUEST');
    });

    it('returns 409 for a concurrent renewal', async () => {
        refreshSpy.mockRejectedValue(
            new AuthRefreshError(AuthRefreshFailure.ConcurrentRefresh),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/session-renewals')
            .send({ refreshToken: 'token' })
            .expect(409);

        const body = response.body as { code: string };
        expect(body.code).toBe('SESSION_REFRESH_CONFLICT');
    });

    it('returns 429 when rate limited', async () => {
        refreshSpy.mockRejectedValue(
            new AuthRefreshError(AuthRefreshFailure.RateLimited),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/session-renewals')
            .send({ refreshToken: 'token' })
            .expect(429);

        const body = response.body as { code: string };
        expect(body.code).toBe('TOO_MANY_REQUESTS');
    });

    it('returns 503 when Supabase is unavailable', async () => {
        refreshSpy.mockRejectedValue(
            new AuthRefreshError(AuthRefreshFailure.ProviderUnavailable),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/session-renewals')
            .send({ refreshToken: 'token' })
            .expect(503);

        const body = response.body as { code: string };
        expect(body.code).toBe('SERVICE_UNAVAILABLE');
    });

    it('documents the endpoint and response in OpenAPI', async () => {
        const response = await request(app.getHttpServer())
            .get('/openapi.json')
            .expect(200);

        const document = response.body as OpenAPIObject;
        const operation = document.paths['/api/v1/session-renewals']?.post;

        expect(operation).toBeDefined();
        expect(operation?.responses['200']).toBeDefined();
        expect(operation?.responses['401']).toBeDefined();
        expect(operation?.responses['409']).toBeDefined();
        expect(operation?.responses['422']).toBeDefined();
        expect(operation?.responses['429']).toBeDefined();
        expect(operation?.responses['503']).toBeDefined();
        expect(document.components?.schemas?.RefreshSessionDto).toBeDefined();
    });

    afterAll(async () => {
        refreshSpy.mockRestore();
        await app.close();
    });
});
