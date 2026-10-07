import {
    HttpException,
    HttpStatus,
    ServiceUnavailableException,
    UnauthorizedException,
} from '@nestjs/common';

import {
    CurrentSessionError,
    CurrentSessionFailure,
} from '../../../application/auth/errors/current-session.error';
import { ProblemCode } from '../common/errors/problem-code';

export function throwCurrentSessionHttpError(error: unknown): never {
    if (!(error instanceof CurrentSessionError)) {
        throw error;
    }

    switch (error.failure) {
        case CurrentSessionFailure.InvalidAccessToken:
            throw new UnauthorizedException({
                code: CurrentSessionFailure.InvalidAccessToken,
                detail: 'The access token is invalid or the session has ended.',
            });
        case CurrentSessionFailure.RateLimited:
            throw new HttpException(
                {
                    code: ProblemCode.TooManyRequests,
                    detail: 'Too many session requests. Try again later.',
                },
                HttpStatus.TOO_MANY_REQUESTS,
            );
        case CurrentSessionFailure.ProviderUnavailable:
            throw new ServiceUnavailableException({
                code: ProblemCode.ServiceUnavailable,
                detail: 'The authentication provider is temporarily unavailable.',
            });
    }
}
