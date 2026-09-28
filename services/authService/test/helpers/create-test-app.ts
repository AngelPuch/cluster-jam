import { INestApplication } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import { App } from 'supertest/types';

import { AppModule } from '../../src/app.module';
import { configureHttpApplication } from '../../src/interfaces/http/http.setup';

export async function createTestApp(): Promise<INestApplication<App>> {
    const moduleFixture = await Test.createTestingModule({
        imports: [AppModule],
    }).compile();

    const app = moduleFixture.createNestApplication();
    configureHttpApplication(app);
    await app.init();

    return app;
}
