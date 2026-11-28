import { HttpStatus, ValidationPipe, type INestApplication } from '@nestjs/common';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import type { NextFunction, Request, Response } from 'express';
import helmet from 'helmet';
import { JsonLogger } from '../../infrastructure/observability/json-logger.service';
import { TraceContextService } from '../../infrastructure/observability/trace-context.service';

export function configureHttpApplication(app: INestApplication): void {
    const tracing = app.get(TraceContextService);
    const logger = app.get(JsonLogger);
    app.use((request: Request, response: Response, next: NextFunction) => {
        tracing.runHttp(request.headers.traceparent, () => {
            response.setHeader('X-Trace-Id', tracing.traceId);
            response.setHeader('Cache-Control', 'no-store');
            const started = performance.now();
            let finished = false;
            const complete = tracing.bindHttp(() => {
                if (finished) return;
                finished = true;
                const status = response.writableFinished ? response.statusCode : 499;
                if (status >= 400 || !request.path.startsWith('/health/')) {
                    const record = {
                        event: 'http.request.completed',
                        status_code: status,
                        duration_ms: Math.round(performance.now() - started),
                    };
                    if (status >= 500) logger.error(record);
                    else logger.log(record);
                }
                tracing.endHttp(status);
            });
            response.once('finish', complete);
            response.once('close', complete);
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
    app.setGlobalPrefix('api/v1', { exclude: ['health/live', 'health/ready'] });
    const config = new DocumentBuilder()
        .setTitle('Cluster JAM Payments Service')
        .setDescription('Payments saga participant: owned payment access, health and signed Stripe webhooks.')
        .addBearerAuth()
        .setVersion('0.0.1')
        .build();
    SwaggerModule.setup('docs', app, SwaggerModule.createDocument(app, config), { jsonDocumentUrl: '/openapi.json' });
}
