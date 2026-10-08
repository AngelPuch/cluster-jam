import {
    ConflictException,
    ForbiddenException,
    HttpException,
    HttpStatus,
    ServiceUnavailableException,
    UnauthorizedException,
    UnprocessableEntityException,
} from '@nestjs/common';

import {
    PasswordRecoveryError,
    PasswordRecoveryFailure,
} from '../../../application/auth/errors/password-recovery.error';
import { ProblemCode } from '../common/errors/problem-code';

export function throwPasswordRecoveryHttpError(error: unknown): never {
    if (!(error instanceof PasswordRecoveryError)) {
        throw error;
    }

    switch (error.failure) {
        case PasswordRecoveryFailure.InvalidRecoveryCode:
            throw new UnauthorizedException({
                code: error.failure,
                detail: 'The recovery code is invalid, expired or already used.',
            });
        case PasswordRecoveryFailure.WeakPassword:
            throw new UnprocessableEntityException({
                code: error.failure,
                detail: 'The password does not meet the required security policy.',
            });
        case PasswordRecoveryFailure.SamePassword:
            throw new ConflictException({
                code: error.failure,
                detail: 'The new password must differ from the current password.',
            });
        case PasswordRecoveryFailure.RecoveryNotAllowed:
            throw new ForbiddenException({
                code: error.failure,
                detail: 'Password recovery is not allowed by the authentication provider.',
            });
        case PasswordRecoveryFailure.InvalidRequest:
            throw new UnprocessableEntityException({
                code: error.failure,
                detail: 'The password recovery data was rejected.',
            });
        case PasswordRecoveryFailure.RateLimited:
            throw new HttpException(
                {
                    code: ProblemCode.TooManyRequests,
                    detail: 'Too many recovery attempts. Try again later.',
                },
                HttpStatus.TOO_MANY_REQUESTS,
            );
        case PasswordRecoveryFailure.ProviderUnavailable:
            throw new ServiceUnavailableException({
                code: ProblemCode.ServiceUnavailable,
                detail: 'The authentication provider is temporarily unavailable.',
            });
    }
}
