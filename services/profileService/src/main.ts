import { NestFactory } from '@nestjs/core';
import { JsonLogger } from './infrastructure/observability/json-logger.service';
import { configureHttpApplication } from './interfaces/http/http.setup';

async function bootstrap() {
    const logger = new JsonLogger();
    const { AppModule } = await import('./app.module.js');
    const app = await NestFactory.create(AppModule, { logger, abortOnError: false });
    configureHttpApplication(app);
    app.enableShutdownHooks();

    const port = process.env.HTTP_PORT ?? 8080;

    await app.listen(port);
    logger.log({ event: 'service.started' });
}

void bootstrap().catch(() => {
    new JsonLogger().error({ event: 'service.failed' });
    process.exitCode = 1;
});
