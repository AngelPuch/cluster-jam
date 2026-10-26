import { HttpStatus, INestApplication, ValidationPipe } from '@nestjs/common';
import helmet from 'helmet';

import { setupOpenApi } from './openapi/openapi.setup';
import { JsonLogger } from '../../infrastructure/observability/json-logger.service';
import { TraceContextService } from '../../infrastructure/observability/trace-context.service';
import { createRequestTelemetry } from './common/observability/request-telemetry.middleware';

interface HttpApplicationOptions {
  enableOpenApi?: boolean;
}

export function configureHttpApplication(
  app: INestApplication,
  options: HttpApplicationOptions = {},
): void {
  app.use(createRequestTelemetry(app.get(JsonLogger), app.get(TraceContextService)));
  app.use(helmet());

  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      forbidNonWhitelisted: true,
      transform: true,
      errorHttpStatusCode: HttpStatus.UNPROCESSABLE_ENTITY,
    }),
  );

  app.setGlobalPrefix('api/v1', {
    exclude: ['health/live', 'health/ready'],
  });

  if (options.enableOpenApi !== false) setupOpenApi(app);
}
