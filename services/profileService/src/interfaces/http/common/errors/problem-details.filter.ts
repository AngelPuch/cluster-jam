import { Catch, HttpException, type ArgumentsHost, type ExceptionFilter } from '@nestjs/common';
import type { Request, Response } from 'express';
import { randomUUID } from 'node:crypto';
import { STATUS_CODES } from 'node:http';
import { AccessTokenError, AccessTokenFailure } from '../../../../application/security/access-token.error';
import { readLogCorrelation } from '../../../../infrastructure/observability/trace-context.service';
import { ProfileError, ProfileFailure } from '../../../../application/profile/profile.error';
import { AddressError, AddressFailure } from '../../../../application/addresses/address.error';

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

const PROFILE_FAILURES: Record<ProfileFailure, { status: number; detail: string }> = {
    [ProfileFailure.NotReady]: { status: 404, detail: 'The profile has not been provisioned yet. Retry later.' },
    [ProfileFailure.InvalidUpdate]: { status: 422, detail: 'Provide at least one valid allowed profile field.' },
    [ProfileFailure.ContactEmailRequired]: {
        status: 422,
        detail: 'Provide a valid contactEmail to update this legacy profile.',
    },
    [ProfileFailure.RevisionMismatch]: { status: 412, detail: 'The profile changed. Read it again before updating.' },
    [ProfileFailure.PersistenceUnavailable]: { status: 503, detail: 'Profile persistence is temporarily unavailable.' },
};
const HTTP_FAILURES: Record<number, { code: string; detail: string }> = {
    400: { code: 'BAD_REQUEST', detail: 'The request syntax or conditional header is invalid.' },
    401: { code: 'INVALID_ACCESS_TOKEN', detail: 'A valid user access token is required.' },
    403: { code: 'FORBIDDEN', detail: 'The operation is not authorized.' },
    404: { code: 'RESOURCE_NOT_FOUND', detail: 'The requested resource was not found.' },
    413: { code: 'PAYLOAD_TOO_LARGE', detail: 'The request body exceeds the allowed size.' },
    415: { code: 'UNSUPPORTED_MEDIA_TYPE', detail: 'Use Content-Type application/json.' },
    422: { code: 'VALIDATION_ERROR', detail: 'The request contains invalid or unknown fields.' },
    428: { code: 'PRECONDITION_REQUIRED', detail: 'Provide the current quoted ETag in If-Match.' },
    503: { code: 'SERVICE_UNAVAILABLE', detail: 'A required dependency is temporarily unavailable.' },
};
const ADDRESS_FAILURES: Record<AddressFailure, { status: number; detail: string }> = {
    [AddressFailure.InvalidInput]: { status: 422, detail: 'Provide valid allowed address fields.' },
    [AddressFailure.NotFound]: { status: 404, detail: 'The requested address was not found.' },
    [AddressFailure.RevisionMismatch]: {
        status: 412,
        detail: 'The address book changed. Read it again before updating.',
    },
    [AddressFailure.PersistenceUnavailable]: { status: 503, detail: 'Address persistence is temporarily unavailable.' },
};

// A single boundary also sanitizes framework/body-parser errors. Never serialize raw exceptions.
@Catch()
export class ProblemDetailsFilter implements ExceptionFilter {
    catch(exception: unknown, host: ArgumentsHost): void {
        const http = host.switchToHttp();
        const request = http.getRequest<Request>();
        const response = http.getResponse<Response>();
        let failure = { status: 500, code: 'INTERNAL_ERROR', detail: 'An unexpected error occurred.' };
        if (exception instanceof AccessTokenError)
            failure = { ...FAILURES[exception.failure], code: exception.failure };
        else if (exception instanceof ProfileError)
            failure = { ...PROFILE_FAILURES[exception.failure], code: exception.failure };
        else if (exception instanceof AddressError)
            failure = { ...ADDRESS_FAILURES[exception.failure], code: exception.failure };
        else if (exception instanceof HttpException) {
            const status = exception.getStatus();
            const known = HTTP_FAILURES[status];
            if (known) failure = { status, ...known };
        }
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
                code: failure.code,
                traceId: readLogCorrelation().trace_id ?? randomUUID().replaceAll('-', ''),
            });
    }
}
