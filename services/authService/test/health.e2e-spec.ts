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
import request from 'supertest';
import { App } from 'supertest/types';

import { createTestApp } from './helpers/create-test-app';

describe('Auth Service health API (e2e)', () => {
    let app: INestApplication<App>;
    let fetchSpy: jest.SpiedFunction<typeof fetch>;

    beforeAll(async () => {
        fetchSpy = jest.spyOn(globalThis, 'fetch');
        app = await createTestApp();
    });

    beforeEach(() => {
        fetchSpy.mockReset();
    });

    it('GET /health/live should return 200', async () => {
        await request(app.getHttpServer())
            .get('/health/live')
            .expect(200)
            .expect({
                status: 'ok',
            });
    });

    it('GET /health/ready should return 200 when Supabase Auth is available', async () => {
        fetchSpy.mockResolvedValueOnce(
            new Response(null, {
                status: 200,
            }),
        );

        await request(app.getHttpServer())
            .get('/health/ready')
            .expect(200)
            .expect({
                status: 'ok',
            });
    });

    it('GET /health/ready should return 503 when Supabase Auth is unavailable', async () => {
        fetchSpy.mockResolvedValueOnce(
            new Response(null, {
                status: 503,
            }),
        );

        const response = await request(app.getHttpServer())
            .get('/health/ready')
            .expect(503)
            .expect('Content-Type', /application\/problem\+json/);

        expect(response.body).toEqual({
            type: 'about:blank',
            title: 'Service Unavailable',
            status: 503,
            detail: 'The service is temporarily unavailable.',
            instance: '/health/ready',
            code: 'SERVICE_UNAVAILABLE',
        });
    });

    afterAll(async () => {
        fetchSpy.mockRestore();
        await app.close();
    });
});
