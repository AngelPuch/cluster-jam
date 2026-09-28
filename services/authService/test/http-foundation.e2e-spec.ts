import { INestApplication } from '@nestjs/common';
import { afterAll, beforeAll, describe, expect, it } from '@jest/globals';
import { OpenAPIObject } from '@nestjs/swagger';
import request from 'supertest';
import { App } from 'supertest/types';

import { createTestApp } from './helpers/create-test-app';
import { ProblemResponse } from './helpers/problem-response';

describe('Auth Service HTTP foundation (e2e)', () => {
    let app: INestApplication<App>;

    beforeAll(async () => {
        app = await createTestApp();
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

        expect(document.paths['/api/v1/registrations']?.post).toBeDefined();

        expect(document.paths['/api/v1/sessions']?.post).toBeDefined();

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
        await app.close();
    });
});
