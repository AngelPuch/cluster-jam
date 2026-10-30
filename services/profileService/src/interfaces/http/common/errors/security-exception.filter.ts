import { Catch, type ArgumentsHost, type ExceptionFilter } from '@nestjs/common';
import type { Request, Response } from 'express';
import { randomUUID } from 'node:crypto';
import { STATUS_CODES } from 'node:http';
import { AccessTokenError, AccessTokenFailure } from '../../../../application/security/access-token.error';
import { readLogCorrelation } from '../../../../infrastructure/observability/trace-context.service';

const FAILURES: Record<AccessTokenFailure, { status: number; detail: string }> = {
    [AccessTokenFailure.InvalidAccessToken]: { status: 401, detail: 'A valid user access token is required.' },
    [AccessTokenFailure.InvalidAppRole]: {
        status: 403,
        detail: 'The identity does not have a valid application role.',
    },
    [AccessTokenFailure.KeysUnavailable]: {
        status: 503,
        detail: 'Required public signing keys are temporarily unavailable.',
    },
};

@Catch(AccessTokenError)
export class SecurityExceptionFilter implements ExceptionFilter<AccessTokenError> {
    catch(exception: AccessTokenError, host: ArgumentsHost): void {
        const http = host.switchToHttp();
        const request = http.getRequest<Request>();
        const response = http.getResponse<Response>();
        const failure = FAILURES[exception.failure];
        if (failure.status === 401) response.setHeader('WWW-Authenticate', 'Bearer');
        response
            .status(failure.status)
            .set('Cache-Control', 'no-store')
            .type('application/problem+json')
            .json({
                type: 'about:blank',
                title: STATUS_CODES[failure.status],
                status: failure.status,
                detail: failure.detail,
                instance: request.originalUrl.split(/[?#]/)[0],
                code: exception.failure,
                traceId: readLogCorrelation().trace_id ?? randomUUID().replaceAll('-', ''),
            });
    }
}
