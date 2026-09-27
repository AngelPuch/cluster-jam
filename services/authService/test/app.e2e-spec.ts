import { INestApplication } from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';
import { OpenAPIObject } from '@nestjs/swagger';
import request from 'supertest';
import { App } from 'supertest/types';
import { afterAll, beforeAll, describe, expect, it, jest } from '@jest/globals';

import { AppModule } from './../src/app.module';
import { configureHttpApplication } from './../src/interfaces/http/http.setup';

interface ProblemResponse {
    type: string;
    title: string;
    status: number;
    detail: string;
    instance: string;
    code: string;
    traceId?: string;
}

describe('Auth Service API foundation (e2e)', () => {
    let app: INestApplication<App>;
    let fetchSpy: jest.SpiedFunction<typeof fetch>;

    beforeAll(async () => {
        fetchSpy = jest.spyOn(globalThis, 'fetch');

        const moduleFixture: TestingModule = await Test.createTestingModule({
            imports: [AppModule],
        }).compile();

        app = moduleFixture.createNestApplication();

        configureHttpApplication(app);

        await app.init();
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

    it('GET /docs should serve Swagger UI', async () => {
        await request(app.getHttpServer())
            .get('/docs')
            .expect(200)
            .expect('Content-Type', /text\/html/);
    });

    it('GET /openapi.json should expose the API contract', async () => {
        const response = await request(app.getHttpServer())
            .get('/openapi.json')
            .expect(200);

        const document = response.body as OpenAPIObject;

        expect(document.info.title).toBe('Cluster JAM Auth Service');

        expect(document.paths['/health/live']?.get).toBeDefined();

        expect(document.paths['/health/ready']?.get).toBeDefined();

        expect(document.paths['/api/v1/health/live']).toBeUndefined();

        expect(document.components?.schemas?.ProblemDetailsDto).toBeDefined();

        expect(
            document.components?.securitySchemes?.['supabase-jwt'],
        ).toBeDefined();

        expect(
            JSON.stringify(document.paths['/health/live']?.get?.responses),
        ).toContain('application/problem+json');
    });

    it('should return RFC 9457 problem details for unknown API routes', async () => {
        const traceId = '4bf92f3577b34da6a3ce929d0e0e4736';

        const response = await request(app.getHttpServer())
            .get('/api/v1/missing')
            .set('traceparent', `00-${traceId}-00f067aa0ba902b7-01`)
            .expect(404)
            .expect('Content-Type', /application\/problem\+json/);

        const body = response.body as ProblemResponse;

        expect(body).toEqual({
            type: 'about:blank',
            title: 'Not Found',
            status: 404,
            detail: 'Cannot GET /api/v1/missing',
            instance: '/api/v1/missing',
            code: 'NOT_FOUND',
            traceId,
        });
    });

    afterAll(async () => {
        fetchSpy.mockRestore();
        await app.close();
    });
});
