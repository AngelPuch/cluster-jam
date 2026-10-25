import {
  ForbiddenException,
  HttpException,
  HttpStatus,
  ServiceUnavailableException,
  UnauthorizedException,
} from '@nestjs/common';

import {
  EmailConfirmationError,
  EmailConfirmationFailure,
} from '../../../application/auth/errors/email-confirmation.error';
import { ProblemCode } from '../common/errors/problem-code';

export function throwEmailConfirmationHttpError(error: unknown): never {
  if (!(error instanceof EmailConfirmationError)) throw error;

  switch (error.failure) {
    case EmailConfirmationFailure.InvalidCode:
      throw new UnauthorizedException({
        code: error.failure,
        detail: 'The confirmation code is invalid, expired or already used.',
      });
    case EmailConfirmationFailure.NotAllowed:
      throw new ForbiddenException({
        code: error.failure,
        detail: 'Email confirmation is not allowed.',
      });
    case EmailConfirmationFailure.RateLimited:
      throw new HttpException(
        {
          code: ProblemCode.TooManyRequests,
          detail: 'Too many confirmation attempts. Try again later.',
        },
        HttpStatus.TOO_MANY_REQUESTS,
      );
    case EmailConfirmationFailure.ProviderUnavailable:
      throw new ServiceUnavailableException({
        code: ProblemCode.ServiceUnavailable,
        detail: 'The authentication provider is temporarily unavailable.',
      });
  }
}
