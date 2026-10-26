import { HttpException } from '@nestjs/common';
import { context, SpanStatusCode } from '@opentelemetry/api';
import type { Request, RequestHandler, Response } from 'express';
import { randomUUID } from 'node:crypto';
import { performance } from 'node:perf_hooks';

import { JsonLogger } from '../../../../infrastructure/observability/json-logger.service';
import { TraceContextService } from '../../../../infrastructure/observability/trace-context.service';

interface HttpFailure {
  unexpected: boolean;
  errorType: 'HttpException' | 'UnexpectedError';
}
const traceIds = new WeakMap<Response, string>();

export function readHttpTraceId(response: Response): string | undefined {
  return traceIds.get(response);
}

const failures = new WeakMap<Response, HttpFailure>();

export function markHttpFailure(response: Response, exception: unknown): void {
  const isHttpException = exception instanceof HttpException;
  failures.set(response, {
    unexpected: !isHttpException || exception.getStatus() === 500,
    errorType: isHttpException ? 'HttpException' : 'UnexpectedError',
  });
}

function routeTemplate(request: Request): string {
  const route: unknown = request.route;
  if (
    typeof route === 'object' &&
    route !== null &&
    'path' in route &&
    typeof route.path === 'string' &&
    /^\/[a-zA-Z0-9/{}:_.-]{0,199}$/.test(route.path)
  )
    return route.path;
  if (request.path === '/docs' || request.path === '/openapi.json') return request.path;
  return 'unmatched';
}

export function createRequestTelemetry(
  logger: JsonLogger,
  tracing: TraceContextService,
): RequestHandler {
  return (request, response, next) => {
    const path = request.path.replace(/\/+$/, '');
    if (path === '/health/live' || path === '/health/ready') {
      next();
      return;
    }
    const startedAt = performance.now();
    const requestId = randomUUID();
    const { span, scope } = tracing.startHttp(request.get('traceparent'), requestId);
    traceIds.set(response, span.spanContext().traceId);
    response.setHeader('X-Request-Id', requestId);
    let completed = false;
    const finish = (): void => {
      if (completed) return;
      completed = true;
      context.with(scope, () => {
        const failure = failures.get(response);
        const disconnected = !response.writableFinished;
        const unexpected = disconnected || failure?.unexpected || response.statusCode === 500;
        const httpRoute = routeTemplate(request);
        span.updateName(`${request.method} ${httpRoute}`);
        span.setAttributes({
          'http.request.method': request.method,
          'http.route': httpRoute,
          'http.response.status_code': response.statusCode,
        });
        if (unexpected) span.setStatus({ code: SpanStatusCode.ERROR });
        const entry = {
          event: 'http.request.completed',
          http_method: request.method,
          http_route: httpRoute,
          status_code: disconnected ? 499 : response.statusCode,
          duration_ms: Math.round((performance.now() - startedAt) * 100) / 100,
          ...(disconnected
            ? { error_type: 'ClientDisconnected' }
            : unexpected
              ? { error_type: failure?.errorType ?? 'UnexpectedError' }
              : {}),
        };
        if (unexpected) logger.error(entry);
        else logger.log(entry);
        span.end();
      });
    };
    response.once('finish', finish);
    response.once('close', finish);
    context.with(scope, next);
  };
}
