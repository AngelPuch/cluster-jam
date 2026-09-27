import {
    ConflictException,
    HttpException,
    HttpStatus,
    ServiceUnavailableException,
    UnprocessableEntityException,
} from '@nestjs/common';

import {
    AuthRegistrationError,
    AuthRegistrationFailure,
} from '../../../application/auth/errors/auth-registration.error';
import { ProblemCode } from '../common/errors/problem-code';

export function throwAuthRegistrationHttpError(error: unknown): never {
    if (!(error instanceof AuthRegistrationError)) {
        throw error;
    }

    switch (error.failure) {
        case AuthRegistrationFailure.EmailAlreadyRegistered:
            throw new ConflictException({
                code: AuthRegistrationFailure.EmailAlreadyRegistered,
                detail: 'An account with this email is already registered.',
            });

        case AuthRegistrationFailure.InvalidEmail:
            throw new UnprocessableEntityException({
                code: AuthRegistrationFailure.InvalidEmail,
                detail: 'The email address is not accepted.',
            });

        case AuthRegistrationFailure.InvalidRequest:
            throw new UnprocessableEntityException({
                code: AuthRegistrationFailure.InvalidRequest,
                detail: 'The registration data was rejected.',
            });

        case AuthRegistrationFailure.WeakPassword:
            throw new UnprocessableEntityException({
                code: AuthRegistrationFailure.WeakPassword,
                detail: 'The password does not meet the required security policy.',
            });

        case AuthRegistrationFailure.RateLimited:
            throw new HttpException(
                {
                    code: ProblemCode.TooManyRequests,
                    detail: 'Too many registration attempts. Try again later.',
                },
                HttpStatus.TOO_MANY_REQUESTS,
            );

        case AuthRegistrationFailure.ProviderUnavailable:
            throw new ServiceUnavailableException({
                code: ProblemCode.ServiceUnavailable,
                detail: 'The authentication provider is temporarily unavailable.',
            });
    }
}
