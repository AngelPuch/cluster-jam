import { Inject, Injectable, type CanActivate, type ExecutionContext } from '@nestjs/common';
import type { Request } from 'express';
import {
    ACCESS_TOKEN_VERIFIER_PORT,
    MAX_ACCESS_TOKEN_LENGTH,
    type AccessTokenVerifierPort,
} from '../../../application/ports/access-token-verifier.port';
import { AccessTokenError, AccessTokenFailure } from '../../../application/security/access-token.error';
import type { VerifiedIdentity } from '../../../application/security/verified-identity';

export interface AuthenticatedRequest extends Request {
    identity?: VerifiedIdentity;
}

@Injectable()
export class JwtAuthGuard implements CanActivate {
    constructor(@Inject(ACCESS_TOKEN_VERIFIER_PORT) private readonly verifier: AccessTokenVerifierPort) {}

    async canActivate(context: ExecutionContext): Promise<boolean> {
        const request = context.switchToHttp().getRequest<AuthenticatedRequest>();
        delete request.identity;
        const authorization = request.headers.authorization;
        const headerCount = request.rawHeaders
            .filter((_, index) => index % 2 === 0)
            .filter((name) => name.toLowerCase() === 'authorization').length;
        const token = typeof authorization === 'string' ? /^Bearer ([^\s]+)$/i.exec(authorization)?.[1] : undefined;
        if (headerCount !== 1 || !token || token.length > MAX_ACCESS_TOKEN_LENGTH) {
            throw new AccessTokenError(AccessTokenFailure.InvalidAccessToken);
        }
        request.identity = await this.verifier.verify(token);
        return true;
    }
}
