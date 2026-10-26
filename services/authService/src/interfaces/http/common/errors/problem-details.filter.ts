import { ArgumentsHost, Catch, ExceptionFilter } from '@nestjs/common';
import { Request, Response } from 'express';

import { markHttpFailure, readHttpTraceId } from '../observability/request-telemetry.middleware';
import { mapExceptionToProblemDetails } from './problem-details.mapper';

@Catch()
export class ProblemDetailsFilter implements ExceptionFilter {
  catch(exception: unknown, host: ArgumentsHost): void {
    const context = host.switchToHttp();

    const request = context.getRequest<Request>();
    const response = context.getResponse<Response>();

    markHttpFailure(response, exception);

    const problemDetails = mapExceptionToProblemDetails(
      exception,
      getRequestPath(request),
      readHttpTraceId(response),
    );

    response
      .status(problemDetails.status)
      .set('Cache-Control', 'no-store')
      .type('application/problem+json')
      .json(problemDetails);
  }
}

function getRequestPath(request: Request): string {
  return request.originalUrl.split(/[?#]/)[0];
}
