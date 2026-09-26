import { ArgumentsHost, Catch, ExceptionFilter } from '@nestjs/common';
import { Request, Response } from 'express';

import { mapExceptionToProblemDetails } from './problem-details.mapper';

const TRACEPARENT_PATTERN =
    /^[0-9a-f]{2}-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$/i;

@Catch()
export class ProblemDetailsFilter implements ExceptionFilter {
    catch(exception: unknown, host: ArgumentsHost): void {
        const context = host.switchToHttp();

        const request = context.getRequest<Request>();
        const response = context.getResponse<Response>();

        const problemDetails = mapExceptionToProblemDetails(
            exception,
            getRequestPath(request),
            extractTraceId(request.get('traceparent')),
        );

        response
            .status(problemDetails.status)
            .type('application/problem+json')
            .json(problemDetails);
    }
}

function extractTraceId(traceparent: string | undefined): string | undefined {
    if (!traceparent) {
        return undefined;
    }

    return TRACEPARENT_PATTERN.exec(traceparent)?.[1];
}

function getRequestPath(request: Request): string {
    return request.originalUrl.split(/[?#]/)[0];
}
