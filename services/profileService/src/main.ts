import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { JsonLogger } from './infrastructure/observability/json-logger.service';

async function bootstrap() {
    const app = await NestFactory.create(AppModule, { bufferLogs: true });
    const logger = app.get(JsonLogger);
    app.useLogger(logger);
    app.enableShutdownHooks();

    const port = process.env.HTTP_PORT ?? 8080;

    await app.listen(port);
    logger.log({ event: 'service.started' });
}

void bootstrap();
