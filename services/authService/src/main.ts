import type { INestApplication } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { NestFactory } from '@nestjs/core';

import { AppModule } from './app.module';
import { JsonLogger } from './infrastructure/observability/json-logger.service';
import { configureHttpApplication } from './interfaces/http/http.setup';

async function bootstrap(): Promise<void> {
  const bootstrapLogger = new JsonLogger();
  let app: INestApplication | undefined;
  try {
    app = await NestFactory.create(AppModule, {
      logger: false,
      abortOnError: false,
    });
    const logger = app.get(JsonLogger);
    configureHttpApplication(app);
    app.enableShutdownHooks();
    const port = app.get(ConfigService).getOrThrow<number>('HTTP_PORT');
    await app.listen(port);
    app.useLogger(logger);
    logger.serviceStarted();
  } catch {
    bootstrapLogger.error({ event: 'service.start.failed' });
    await app?.close().catch(() => {
      process.exitCode = 1;
    });
    process.exitCode = 1;
  }
}

void bootstrap();
