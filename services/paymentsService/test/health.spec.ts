import { Test } from '@nestjs/testing';
import type { INestApplication } from '@nestjs/common';
import { jest } from '@jest/globals';
import request from 'supertest';
import { APP_FILTER } from '@nestjs/core';
import { DatabaseReadiness } from '../src/infrastructure/database/database-readiness.service';
import { ObservabilityModule } from '../src/infrastructure/observability/observability.module';
import { HealthController } from '../src/interfaces/http/health/health.controller';
import { ProblemDetailsFilter } from '../src/interfaces/http/common/problem-details.filter';
import { configureHttpApplication } from '../src/interfaces/http/http.setup';

describe('Payments foundation HTTP', () => {
    let app: INestApplication;
    const database = { check: jest.fn<() => Promise<boolean>>() };

    beforeAll(async () => {
        const module = await Test.createTestingModule({
            imports: [ObservabilityModule],
            controllers: [HealthController],
            providers: [
                { provide: DatabaseReadiness, useValue: database },
                { provide: APP_FILTER, useClass: ProblemDetailsFilter },
            ],
        }).compile();
        app = module.createNestApplication({ logger: false });
        configureHttpApplication(app);
        await app.init();
    });
    afterAll(async () => {
        await app?.close();
    });

    it('keeps liveness independent from an unavailable database', async () => {
        database.check.mockResolvedValue(false);
        const http = app.getHttpServer() as Parameters<typeof request>[0];
        await request(http).get('/health/live').expect(200, { status: 'ok' });
        expect(database.check).not.toHaveBeenCalled();
        const response = await request(http).get('/health/ready').expect(503);
        expect(response.body).toMatchObject({ status: 503, code: 'SERVICE_UNAVAILABLE' });
        expect(response.headers['content-type']).toContain('application/problem+json');
        expect(response.headers['x-trace-id']).toMatch(/^[0-9a-f]{32}$/);
    });

    it('reports recovery and documents only implemented routes', async () => {
        database.check.mockResolvedValue(true);
        const http = app.getHttpServer() as Parameters<typeof request>[0];
        await request(http).get('/health/ready').expect(200, { status: 'ok' });
        const contract = await request(http).get('/openapi.json').expect(200);
        expect(Object.keys((contract.body as { paths: object }).paths).sort()).toEqual([
            '/health/live',
            '/health/ready',
        ]);
        await request(http).post('/api/v1/payments').send({ amountCents: 1 }).expect(404);
    });
});
