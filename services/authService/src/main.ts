import { ConfigService } from '@nestjs/config';
import { NestFactory } from '@nestjs/core';

import { AppModule } from './app.module';
import { configureHttpApplication } from './interfaces/http/http.setup';

async function bootstrap(): Promise<void> {
    const app = await NestFactory.create(AppModule);

    configureHttpApplication(app);

    const configService = app.get(ConfigService);

    const port = configService.getOrThrow<number>('HTTP_PORT');

    await app.listen(port);
}

void bootstrap();
