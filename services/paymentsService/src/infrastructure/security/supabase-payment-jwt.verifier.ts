import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { isUUID } from 'class-validator';
import { createRemoteJWKSet, decodeProtectedHeader, errors, jwtVerify } from 'jose';
import type { PaymentTokenVerifier } from '../../application/ports/payment-access.port';
import { InvalidPaymentToken, PaymentKeysUnavailable } from '../../application/payments/payment-access.error';
const ALGORITHMS = ['ES256', 'RS256'];
@Injectable()
export class SupabasePaymentJwtVerifier implements PaymentTokenVerifier {
    private readonly issuer?: string;
    private readonly jwks?: ReturnType<typeof createRemoteJWKSet>;
    constructor(config: ConfigService) {
        const project = config.get<string>('SUPABASE_URL');
        if (!project) return;
        this.issuer = new URL(project).origin + '/auth/v1';
        this.jwks = createRemoteJWKSet(new URL(this.issuer + '/.well-known/jwks.json'), {
            timeoutDuration: 5000,
            cacheMaxAge: 600000,
            cooldownDuration: 30000,
        });
    }
    async verify(token: string): Promise<string> {
        const jwks = this.jwks;
        if (!jwks || !this.issuer) throw new PaymentKeysUnavailable();
        try {
            if (!token || token.length > 16384) throw new InvalidPaymentToken();
            const header = decodeProtectedHeader(token);
            if (
                !ALGORITHMS.includes(String(header.alg)) ||
                typeof header.kid !== 'string' ||
                !header.kid.trim() ||
                header.kid.length > 256
            )
                throw new InvalidPaymentToken();
            const { payload } = await jwtVerify(
                token,
                async (protectedHeader, jwt) => {
                    try {
                        return await jwks(protectedHeader, jwt);
                    } catch (error) {
                        if (error instanceof errors.JWKSNoMatchingKey && jwks.jwks()?.keys.length)
                            throw new InvalidPaymentToken();
                        throw new PaymentKeysUnavailable();
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
            )
                throw new InvalidPaymentToken();
            return payload.sub.toLowerCase();
        } catch (error) {
            if (error instanceof PaymentKeysUnavailable) throw error;
            throw new InvalidPaymentToken();
        }
    }
}
