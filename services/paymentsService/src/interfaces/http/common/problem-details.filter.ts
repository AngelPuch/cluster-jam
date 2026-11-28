import { Catch, HttpException, type ArgumentsHost, type ExceptionFilter } from '@nestjs/common';
import type { Request, Response } from 'express';
import { randomUUID } from 'node:crypto';
import { STATUS_CODES } from 'node:http';
import { readLogCorrelation } from '../../../infrastructure/observability/trace-context.service';

const FAILURES: Record<number, { code: string; detail: string }> = {
    400: { code: 'BAD_REQUEST', detail: 'The request syntax is invalid.' },
    404: { code: 'RESOURCE_NOT_FOUND', detail: 'The requested resource was not found.' },
    413: { code: 'PAYLOAD_TOO_LARGE', detail: 'The request exceeds the allowed size.' },
    415: { code: 'UNSUPPORTED_MEDIA_TYPE', detail: 'Use a supported content type.' },
    422: { code: 'VALIDATION_ERROR', detail: 'The request contains invalid fields.' },
    500: { code: 'INTERNAL_ERROR', detail: 'An unexpected error occurred.' },
    503: { code: 'SERVICE_UNAVAILABLE', detail: 'A required dependency is temporarily unavailable.' },
};

@Catch()
export class ProblemDetailsFilter implements ExceptionFilter {
    catch(error: unknown, host: ArgumentsHost): void {
        const http = host.switchToHttp();
        const request = http.getRequest<Request>();
        const response = http.getResponse<Response>();
        const requestedStatus = error instanceof HttpException ? error.getStatus() : 500;
        const status = Object.hasOwn(FAILURES, requestedStatus) ? requestedStatus : 500;
        response
            .status(status)
            .set('Cache-Control', 'no-store')
            .type('application/problem+json')
            .json({
                type: 'about:blank',
                title: STATUS_CODES[status],
                status,
                ...FAILURES[status],
                instance: request.originalUrl.split(/[?#]/)[0],
                traceId: readLogCorrelation().trace_id ?? randomUUID().replaceAll('-', ''),
            });
    }
}
