import { createParamDecorator, type ExecutionContext } from '@nestjs/common';
import type { VerifiedIdentity } from '../../../application/security/verified-identity';
import { AccessTokenError, AccessTokenFailure } from '../../../application/security/access-token.error';
import type { AuthenticatedRequest } from './jwt-auth.guard';

export const CurrentIdentity = createParamDecorator((_data: unknown, context: ExecutionContext): VerifiedIdentity => {
    const identity = context.switchToHttp().getRequest<AuthenticatedRequest>().identity;
    if (!identity) throw new AccessTokenError(AccessTokenFailure.InvalidAccessToken);
    return identity;
});
