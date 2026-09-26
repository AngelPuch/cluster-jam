import { HttpException, HttpStatus } from '@nestjs/common';
import { STATUS_CODES } from 'node:http';

import { ProblemCode } from './problem-code';
import { ProblemDetailsDto } from './problem-details.dto';

type ExceptionResponse = Record<string, unknown>;

const PROBLEM_CODE_MAP: Record<number, ProblemCode> = {
    [HttpStatus.BAD_REQUEST]: ProblemCode.BadRequest,
    [HttpStatus.UNAUTHORIZED]: ProblemCode.Unauthorized,
    [HttpStatus.FORBIDDEN]: ProblemCode.Forbidden,
    [HttpStatus.NOT_FOUND]: ProblemCode.NotFound,
    [HttpStatus.METHOD_NOT_ALLOWED]: ProblemCode.MethodNotAllowed,
    [HttpStatus.CONFLICT]: ProblemCode.Conflict,
    [HttpStatus.PAYLOAD_TOO_LARGE]: ProblemCode.PayloadTooLarge,
    [HttpStatus.UNSUPPORTED_MEDIA_TYPE]: ProblemCode.UnsupportedMediaType,
    [HttpStatus.UNPROCESSABLE_ENTITY]: ProblemCode.UnprocessableEntity,
    [HttpStatus.TOO_MANY_REQUESTS]: ProblemCode.TooManyRequests,
    [HttpStatus.INTERNAL_SERVER_ERROR]: ProblemCode.InternalServerError,
    [HttpStatus.BAD_GATEWAY]: ProblemCode.BadGateway,
    [HttpStatus.SERVICE_UNAVAILABLE]: ProblemCode.ServiceUnavailable,
    [HttpStatus.GATEWAY_TIMEOUT]: ProblemCode.GatewayTimeout,
};

export function mapExceptionToProblemDetails(
    exception: unknown,
    instance: string,
    traceId?: string,
): ProblemDetailsDto {
    const status =
        exception instanceof HttpException
            ? exception.getStatus()
            : HttpStatus.INTERNAL_SERVER_ERROR;

    const response =
        exception instanceof HttpException
            ? exception.getResponse()
            : undefined;

    const responseObject = isRecord(response) ? response : undefined;

    const validationErrors = getValidationErrors(responseObject?.message);

    const code =
        getString(responseObject?.code) ??
        (validationErrors
            ? ProblemCode.ValidationError
            : getDefaultProblemCode(status));

    const type = getString(responseObject?.type) ?? 'about:blank';

    const detail = getDetail(
        status,
        response,
        responseObject,
        validationErrors,
    );

    return {
        type,
        title: STATUS_CODES[status] ?? 'Error',
        status,
        detail,
        instance,
        code,
        ...(validationErrors ? { errors: validationErrors } : {}),
        ...(traceId ? { traceId } : {}),
    };
}

function getDetail(
    status: HttpStatus,
    response: string | object | undefined,
    responseObject: ExceptionResponse | undefined,
    validationErrors: string[] | undefined,
): string {
    const explicitDetail = getString(responseObject?.detail);

    if (explicitDetail) {
        return explicitDetail;
    }

    if (status >= HttpStatus.INTERNAL_SERVER_ERROR) {
        return getServerErrorDetail(status);
    }

    if (validationErrors) {
        return 'Request validation failed.';
    }

    if (typeof response === 'string') {
        return response;
    }

    return (
        getString(responseObject?.message) ??
        STATUS_CODES[status] ??
        'Request failed.'
    );
}

function getServerErrorDetail(status: HttpStatus): string {
    if (
        status === HttpStatus.BAD_GATEWAY ||
        status === HttpStatus.SERVICE_UNAVAILABLE ||
        status === HttpStatus.GATEWAY_TIMEOUT
    ) {
        return 'The service is temporarily unavailable.';
    }

    return 'An unexpected error occurred.';
}

function getDefaultProblemCode(status: number): ProblemCode {
    return PROBLEM_CODE_MAP[status] ?? ProblemCode.HttpError;
}

function getValidationErrors(value: unknown): string[] | undefined {
    if (!Array.isArray(value)) {
        return undefined;
    }

    const errors = value.filter(
        (item): item is string => typeof item === 'string',
    );

    return errors.length > 0 ? errors : undefined;
}

function getString(value: unknown): string | undefined {
    return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function isRecord(value: unknown): value is ExceptionResponse {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}
