import { INestApplication } from '@nestjs/common';
import {
    afterAll,
    beforeAll,
    beforeEach,
    describe,
    expect,
    it,
    jest,
} from '@jest/globals';
import { OpenAPIObject } from '@nestjs/swagger';
import request from 'supertest';
import { App } from 'supertest/types';

import {
    CurrentSessionError,
    CurrentSessionFailure,
} from '../src/application/auth/errors/current-session.error';
import {
    CURRENT_SESSION_PORT,
    type CurrentSessionPort,
} from '../src/application/ports/current-session.port';
import { createTestApp } from './helpers/create-test-app';

describe('Current session API (e2e)', () => {
    let app: INestApplication<App>;
    let getSpy: jest.SpiedFunction<CurrentSessionPort['getCurrentIdentity']>;
    let endSpy: jest.SpiedFunction<CurrentSessionPort['endCurrentSession']>;

    beforeAll(async () => {
        app = await createTestApp();
        const provider = app.get<CurrentSessionPort>(CURRENT_SESSION_PORT);
        getSpy = jest.spyOn(provider, 'getCurrentIdentity');
        endSpy = jest.spyOn(provider, 'endCurrentSession');
    });

    beforeEach(() => {
        getSpy.mockReset();
        endSpy.mockReset();
    });

    it('gets the current identity without exposing tokens', async () => {
        const identity = {
            userId: '11111111-1111-4111-8111-111111111111',
            email: 'user@example.com',
        };
        getSpy.mockResolvedValue(identity);
        const response = await request(app.getHttpServer())
            .get('/api/v1/sessions/current')
            .set('Authorization', 'Bearer access-token')
            .expect(200);
        expect(response.headers['cache-control']).toBe('no-store');
        expect(response.body).toEqual(identity);
        expect(getSpy).toHaveBeenCalledWith('access-token');
    });

    it('ends the current session with 204 and no response body', async () => {
        endSpy.mockResolvedValue();
        const response = await request(app.getHttpServer())
            .delete('/api/v1/sessions/current')
            .set('Authorization', 'Bearer access-token')
            .expect(204);
        expect(response.text).toBe('');
        expect(endSpy).toHaveBeenCalledWith('access-token');
    });

    it('rejects missing and malformed Authorization on both routes', async () => {
        for (const method of ['get', 'delete'] as const) {
            for (const value of [undefined, 'Basic fake', 'Bearer a b']) {
                let req = request(app.getHttpServer())[method](
                    '/api/v1/sessions/current',
                );
                if (value) req = req.set('Authorization', value);
                const response = await req.expect(401);
                expect(response.body).toMatchObject({
                    status: 401,
                    code: 'INVALID_ACCESS_TOKEN',
                    instance: '/api/v1/sessions/current',
                });
            }
        }
        expect(getSpy).not.toHaveBeenCalled();
        expect(endSpy).not.toHaveBeenCalled();
    });

    it('maps an ended session and provider failure to Problem Details', async () => {
        getSpy.mockRejectedValueOnce(
            new CurrentSessionError(CurrentSessionFailure.InvalidAccessToken),
        );
        const invalid = await request(app.getHttpServer())
            .get('/api/v1/sessions/current')
            .set('Authorization', 'Bearer secret-token')
            .expect(401);
        expect((invalid.body as { code: string }).code).toBe(
            'INVALID_ACCESS_TOKEN',
        );
        expect(JSON.stringify(invalid.body)).not.toContain('secret-token');
        endSpy.mockRejectedValueOnce(
            new CurrentSessionError(CurrentSessionFailure.ProviderUnavailable),
        );
        const outage = await request(app.getHttpServer())
            .delete('/api/v1/sessions/current')
            .set('Authorization', 'Bearer secret-token')
            .expect(503);
        expect((outage.body as { code: string }).code).toBe(
            'SERVICE_UNAVAILABLE',
        );
    });

    it('returns 429 when Supabase limits session requests', async () => {
        getSpy.mockRejectedValueOnce(
            new CurrentSessionError(CurrentSessionFailure.RateLimited),
        );
        const response = await request(app.getHttpServer())
            .get('/api/v1/sessions/current')
            .set('Authorization', 'Bearer access-token')
            .expect(429);
        expect((response.body as { code: string }).code).toBe(
            'TOO_MANY_REQUESTS',
        );
    });

    it('publishes bearer security and responses in OpenAPI', async () => {
        const response = await request(app.getHttpServer())
            .get('/openapi.json')
            .expect(200);
        const doc = response.body as OpenAPIObject;
        const path = doc.paths['/api/v1/sessions/current'];
        expect(path?.get?.responses['200']).toBeDefined();
        expect(path?.delete?.responses['204']).toBeDefined();
        for (const op of [path?.get, path?.delete]) {
            expect(op?.security).toEqual([{ 'supabase-jwt': [] }]);
            expect(op?.responses['401']).toBeDefined();
            expect(op?.responses['429']).toBeDefined();
            expect(op?.responses['503']).toBeDefined();
        }
        expect(
            doc.components?.schemas?.CurrentIdentityResponseDto,
        ).toBeDefined();
    });

    afterAll(async () => {
        getSpy.mockRestore();
        endSpy.mockRestore();
        await app.close();
    });
});
