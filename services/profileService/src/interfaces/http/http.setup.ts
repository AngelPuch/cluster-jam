import { HttpStatus, ValidationPipe, type INestApplication } from '@nestjs/common';
import helmet from 'helmet';
import type { NextFunction, Request, Response } from 'express';
import { JsonLogger } from '../../infrastructure/observability/json-logger.service';
import { TraceContextService } from '../../infrastructure/observability/trace-context.service';
import { configureApiPrefix, setupOpenApi } from './openapi/openapi.setup';

export function configureHttpApplication(app: INestApplication): void {
    const tracing = app.get(TraceContextService);
    const logger = app.get(JsonLogger);
    app.use((request: Request, response: Response, next: NextFunction) => {
        tracing.runHttp(request.headers.traceparent, () => {
            response.setHeader('X-Trace-Id', tracing.traceId);
            const started = performance.now();
            let finished = false;
            const complete = () => {
                if (finished) return;
                finished = true;
                const status = response.writableFinished ? response.statusCode : 499;
                if (status >= 400 || !request.path.startsWith('/health/')) {
                    const input = {
                        event: 'http.request.completed',
                        http_status: status,
                        duration_ms: Math.round(performance.now() - started),
                    };
                    if (status >= 500) logger.error(input);
                    else logger.log(input);
                }
                tracing.endHttp(status);
            };
            const onComplete = tracing.bindHttp(complete);
            response.once('finish', onComplete);
            response.once('close', onComplete);
            next();
        });
    });
    app.use(helmet());
    app.useGlobalPipes(
        new ValidationPipe({
            whitelist: true,
            forbidNonWhitelisted: true,
            transform: true,
            errorHttpStatusCode: HttpStatus.UNPROCESSABLE_ENTITY,
            validationError: { target: false, value: false },
        }),
    );
    configureApiPrefix(app);
    setupOpenApi(app);
}
