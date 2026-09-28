import {
    ForbiddenException,
    HttpException,
    HttpStatus,
    ServiceUnavailableException,
    UnauthorizedException,
    UnprocessableEntityException,
} from '@nestjs/common';

import {
    AuthLoginError,
    AuthLoginFailure,
} from '../../../application/auth/errors/auth-login.error';
import { ProblemCode } from '../common/errors/problem-code';

export function throwAuthLoginHttpError(error: unknown): never {
    if (!(error instanceof AuthLoginError)) {
        throw error;
    }

    switch (error.failure) {
        case AuthLoginFailure.InvalidCredentials:
            throw new UnauthorizedException({
                code: AuthLoginFailure.InvalidCredentials,
                detail: 'The email or password is incorrect.',
            });

        case AuthLoginFailure.EmailNotConfirmed:
            throw new ForbiddenException({
                code: AuthLoginFailure.EmailNotConfirmed,
                detail: 'The email address must be confirmed before signing in.',
            });

        case AuthLoginFailure.InvalidRequest:
            throw new UnprocessableEntityException({
                code: AuthLoginFailure.InvalidRequest,
                detail: 'The login data was rejected.',
            });

        case AuthLoginFailure.RateLimited:
            throw new HttpException(
                {
                    code: ProblemCode.TooManyRequests,
                    detail: 'Too many login attempts. Try again later.',
                },
                HttpStatus.TOO_MANY_REQUESTS,
            );

        case AuthLoginFailure.ProviderUnavailable:
            throw new ServiceUnavailableException({
                code: ProblemCode.ServiceUnavailable,
                detail: 'The authentication provider is temporarily unavailable.',
            });
    }
}
