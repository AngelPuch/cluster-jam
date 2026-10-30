import { Test } from '@nestjs/testing';
import type { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { DataSource } from 'typeorm';
import { HealthController } from '../src/interfaces/http/health/health.controller';
import { jest } from '@jest/globals';
import { RabbitMqListener } from '../src/infrastructure/messaging/rabbitmq-listener';

describe('Health HTTP contract', () => {
    let app: INestApplication;
    const database = { isInitialized: true, query: jest.fn<() => Promise<unknown[]>>().mockResolvedValue([]) };
    const broker = { isReady: true };

    beforeAll(async () => {
        const module = await Test.createTestingModule({
            controllers: [HealthController],
            providers: [
                { provide: DataSource, useValue: database },
                { provide: RabbitMqListener, useValue: broker },
            ],
        }).compile();
        app = module.createNestApplication();
        await app.init();
    });
    afterAll(async () => {
        await app?.close();
    });

    it('reports liveness without querying dependencies', async () => {
        database.query.mockClear();
        await request(app.getHttpServer() as Parameters<typeof request>[0])
            .get('/health/live')
            .expect(200, { status: 'ok' });
        expect(database.query).not.toHaveBeenCalled();
    });

    it('checks database readiness', async () => {
        await request(app.getHttpServer() as Parameters<typeof request>[0])
            .get('/health/ready')
            .expect(200);
        expect(database.query).toHaveBeenCalledWith('SELECT 1');
    });

    it('returns 503 when the database is not initialized', async () => {
        database.isInitialized = false;
        await request(app.getHttpServer() as Parameters<typeof request>[0])
            .get('/health/ready')
            .expect(503);
        database.isInitialized = true;
    });

    it('returns 503 without exposing database errors when the readiness query fails', async () => {
        database.query.mockRejectedValueOnce(new Error('private database failure'));
        const response = await request(app.getHttpServer() as Parameters<typeof request>[0])
            .get('/health/ready')
            .expect(503);
        expect(response.text).not.toContain('private database failure');
    });

    it('returns 503 while the consumer is disconnected without affecting liveness', async () => {
        broker.isReady = false;
        await request(app.getHttpServer() as Parameters<typeof request>[0])
            .get('/health/ready')
            .expect(503);
        await request(app.getHttpServer() as Parameters<typeof request>[0])
            .get('/health/live')
            .expect(200);
        broker.isReady = true;
    });
});
