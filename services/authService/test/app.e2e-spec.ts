import { INestApplication } from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';
import request from 'supertest';
import { App } from 'supertest/types';

import { AppModule } from './../src/app.module';

describe('Health endpoints (e2e)', () => {
    let app: INestApplication<App>;

    beforeAll(async () => {
        const moduleFixture: TestingModule = await Test.createTestingModule({
            imports: [AppModule],
        }).compile();

        app = moduleFixture.createNestApplication();

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

    it('GET /health/ready should return 200', async () => {
        await request(app.getHttpServer())
            .get('/health/ready')
            .expect(200)
            .expect({
                status: 'ok',
            });
    });

    afterAll(async () => {
        await app.close();
    });
});
