import {
    ConflictException,
    HttpException,
    HttpStatus,
    ServiceUnavailableException,
    UnauthorizedException,
    UnprocessableEntityException,
} from '@nestjs/common';

import {
    AuthRefreshError,
    AuthRefreshFailure,
} from '../../../application/auth/errors/auth-refresh.error';
import { ProblemCode } from '../common/errors/problem-code';

export function throwAuthRefreshHttpError(error: unknown): never {
    if (!(error instanceof AuthRefreshError)) {
        throw error;
    }

    switch (error.failure) {
        case AuthRefreshFailure.InvalidRefreshToken:
            throw new UnauthorizedException({
                code: AuthRefreshFailure.InvalidRefreshToken,
                detail: 'The refresh token is invalid or the session has ended.',
            });

        case AuthRefreshFailure.InvalidRequest:
            throw new UnprocessableEntityException({
                code: AuthRefreshFailure.InvalidRequest,
                detail: 'The session renewal data was rejected.',
            });

        case AuthRefreshFailure.ConcurrentRefresh:
            throw new ConflictException({
                code: AuthRefreshFailure.ConcurrentRefresh,
                detail: 'The session is being renewed concurrently.',
            });

        case AuthRefreshFailure.RateLimited:
            throw new HttpException(
                {
                    code: ProblemCode.TooManyRequests,
                    detail: 'Too many renewal attempts. Try again later.',
                },
                HttpStatus.TOO_MANY_REQUESTS,
            );

        case AuthRefreshFailure.ProviderUnavailable:
            throw new ServiceUnavailableException({
                code: ProblemCode.ServiceUnavailable,
                detail: 'The authentication provider is temporarily unavailable.',
            });
    }
}
