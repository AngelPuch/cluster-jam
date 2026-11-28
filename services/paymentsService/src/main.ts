import { NestFactory } from '@nestjs/core';
import { JsonLogger } from './infrastructure/observability/json-logger.service';
import { configureHttpApplication } from './interfaces/http/http.setup';

async function bootstrap(): Promise<void> {
    const logger = new JsonLogger();
    const { AppModule } = await import('./app.module.js');
    const app = await NestFactory.create(AppModule, { logger, rawBody: true, abortOnError: false });
    configureHttpApplication(app);
    app.enableShutdownHooks();
    await app.listen(Number(process.env.HTTP_PORT ?? 8085));
    logger.log({ event: 'service.started' });
}

void bootstrap().catch(() => {
    new JsonLogger().error({ event: 'service.failed' });
    process.exitCode = 1;
});
