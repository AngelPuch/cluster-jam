import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { createRemoteJWKSet, decodeProtectedHeader, errors, jwtVerify } from 'jose';
import { isUUID } from 'class-validator';
import {
    MAX_ACCESS_TOKEN_LENGTH,
    type AccessTokenVerifierPort,
} from '../../application/ports/access-token-verifier.port';
import { AccessTokenError, AccessTokenFailure } from '../../application/security/access-token.error';
import { AppRole, type VerifiedIdentity } from '../../application/security/verified-identity';
import { validateSecurityEnvironment } from '../config/security-environment.validation';

const ALGORITHMS = ['ES256', 'RS256'];

@Injectable()
export class SupabaseJwtVerifier implements AccessTokenVerifierPort {
    private readonly issuer: string;
    private readonly jwks: ReturnType<typeof createRemoteJWKSet>;

    constructor(config: ConfigService) {
        const settings = validateSecurityEnvironment({
            APP_ENV: config.get<string>('APP_ENV'),
            SUPABASE_URL: config.get<string>('SUPABASE_URL'),
            SUPABASE_ISSUER: config.get<string>('SUPABASE_ISSUER'),
            SUPABASE_JWKS_URL: config.get<string>('SUPABASE_JWKS_URL'),
            SUPABASE_AUDIENCE: config.get<string>('SUPABASE_AUDIENCE'),
        });
        this.issuer = String(settings.SUPABASE_ISSUER);
        this.jwks = createRemoteJWKSet(new URL(String(settings.SUPABASE_JWKS_URL)), {
            timeoutDuration: 5000,
            cacheMaxAge: 600000,
            cooldownDuration: 30000,
        });
    }

    async verify(accessToken: string): Promise<VerifiedIdentity> {
        try {
            if (
                typeof accessToken !== 'string' ||
                accessToken.length === 0 ||
                accessToken.length > MAX_ACCESS_TOKEN_LENGTH
            ) {
                throw new AccessTokenError(AccessTokenFailure.InvalidAccessToken);
            }
            const header = decodeProtectedHeader(accessToken);
            if (
                !ALGORITHMS.includes(String(header.alg)) ||
                typeof header.kid !== 'string' ||
                !header.kid.trim() ||
                header.kid.length > 256
            ) {
                throw new AccessTokenError(AccessTokenFailure.InvalidAccessToken);
            }
            const { payload } = await jwtVerify(
                accessToken,
                async (protectedHeader, token) => {
                    try {
                        return await this.jwks(protectedHeader, token);
                    } catch (error) {
                        if (error instanceof errors.JWKSNoMatchingKey) {
                            // An empty published set is a provider outage; an unknown
                            // kid in a populated set is an invalid credential.
                            const failure =
                                this.jwks.jwks()?.keys.length === 0
                                    ? AccessTokenFailure.KeysUnavailable
                                    : AccessTokenFailure.InvalidAccessToken;
                            throw new AccessTokenError(failure);
                        }
                        throw new AccessTokenError(AccessTokenFailure.KeysUnavailable);
                    }
                },
                {
                    issuer: this.issuer,
                    audience: 'authenticated',
                    algorithms: ALGORITHMS,
                    requiredClaims: ['sub', 'exp', 'iss', 'aud'],
                },
            );
            if (
                typeof payload.sub !== 'string' ||
                !isUUID(payload.sub) ||
                typeof payload.exp !== 'number' ||
                !Number.isFinite(payload.exp) ||
                payload.role !== 'authenticated' ||
                (payload.is_anonymous !== undefined && payload.is_anonymous !== false)
            ) {
                throw new AccessTokenError(AccessTokenFailure.InvalidAccessToken);
            }
            const metadata = payload.app_metadata;
            const role =
                typeof metadata === 'object' && metadata !== null && !Array.isArray(metadata)
                    ? (metadata as Record<string, unknown>).app_role
                    : undefined;
            if (role !== AppRole.Client && role !== AppRole.Administrator) {
                throw new AccessTokenError(AccessTokenFailure.InvalidAppRole);
            }
            return Object.freeze({ userId: payload.sub.toLowerCase(), appRole: role });
        } catch (error) {
            if (error instanceof AccessTokenError) throw error;
            throw new AccessTokenError(AccessTokenFailure.InvalidAccessToken);
        }
    }
}
