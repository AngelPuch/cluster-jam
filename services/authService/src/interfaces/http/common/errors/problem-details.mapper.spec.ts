import {
    UnauthorizedException,
    UnprocessableEntityException,
} from '@nestjs/common';

import { ProblemCode } from './problem-code';
import { mapExceptionToProblemDetails } from './problem-details.mapper';

describe('mapExceptionToProblemDetails', () => {
    it('should map validation errors to a stable validation code', () => {
        const exception = new UnprocessableEntityException({
            statusCode: 422,
            error: 'Unprocessable Entity',
            message: [
                'email must be an email',
                'password must be longer than or equal to 8 characters',
            ],
        });

        expect(
            mapExceptionToProblemDetails(exception, '/api/v1/example'),
        ).toEqual({
            type: 'about:blank',
            title: 'Unprocessable Entity',
            status: 422,
            detail: 'Request validation failed.',
            instance: '/api/v1/example',
            code: ProblemCode.ValidationError,
            errors: [
                'email must be an email',
                'password must be longer than or equal to 8 characters',
            ],
        });
    });

    it('should preserve an explicit stable error code and detail', () => {
        const exception = new UnauthorizedException({
            code: 'CUSTOM_ERROR',
            detail: 'The operation could not be authorized.',
        });

        expect(
            mapExceptionToProblemDetails(exception, '/api/v1/example'),
        ).toEqual({
            type: 'about:blank',
            title: 'Unauthorized',
            status: 401,
            detail: 'The operation could not be authorized.',
            instance: '/api/v1/example',
            code: 'CUSTOM_ERROR',
        });
    });

    it('should hide internal details from unexpected errors', () => {
        const exception = new Error('Sensitive internal implementation detail');

        expect(
            mapExceptionToProblemDetails(exception, '/api/v1/example'),
        ).toEqual({
            type: 'about:blank',
            title: 'Internal Server Error',
            status: 500,
            detail: 'An unexpected error occurred.',
            instance: '/api/v1/example',
            code: ProblemCode.InternalServerError,
        });
    });
});
