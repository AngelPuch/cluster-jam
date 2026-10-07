import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import {
    createRemoteJWKSet,
    decodeProtectedHeader,
    errors,
    jwtVerify,
} from 'jose';

import {
    CurrentSessionError,
    CurrentSessionFailure,
} from '../../application/auth/errors/current-session.error';
import {
    type CurrentIdentity,
    type CurrentSessionPort,
} from '../../application/ports/current-session.port';

const AUTH_TIMEOUT_MS = 5_000;
const ASYMMETRIC_ALGORITHMS = ['ES256', 'RS256'];

@Injectable()
export class SupabaseCurrentSessionAdapter implements CurrentSessionPort {
    private readonly userUrl: string;
    private readonly logoutUrl: string;
    private readonly issuer: string;
    private readonly publishableKey: string;
    private readonly jwks: ReturnType<typeof createRemoteJWKSet>;

    constructor(config: ConfigService) {
        const supabaseUrl = config.getOrThrow<string>('SUPABASE_URL');
        this.publishableKey = config.getOrThrow<string>(
            'SUPABASE_PUBLISHABLE_KEY',
        );
        this.issuer = new URL('/auth/v1', supabaseUrl).toString();
        this.userUrl = new URL('/auth/v1/user', supabaseUrl).toString();
        this.logoutUrl = new URL(
            '/auth/v1/logout?scope=local',
            supabaseUrl,
        ).toString();
        this.jwks = createRemoteJWKSet(
            new URL(config.getOrThrow<string>('SUPABASE_JWKS_URL')),
            { timeoutDuration: AUTH_TIMEOUT_MS, cacheMaxAge: 600_000 },
        );
    }

    async getCurrentIdentity(accessToken: string): Promise<CurrentIdentity> {
        await this.verifyTokenWhenAsymmetric(accessToken);

        let response: Response;
        try {
            response = await fetch(this.userUrl, {
                method: 'GET',
                headers: {
                    apikey: this.publishableKey,
                    Authorization: `Bearer ${accessToken}`,
                    Accept: 'application/json',
                },
                signal: AbortSignal.timeout(AUTH_TIMEOUT_MS),
            });
        } catch {
            throw new CurrentSessionError(
                CurrentSessionFailure.ProviderUnavailable,
            );
        }

        this.assertSuccessfulStatus(response, 200);
        try {
            const user: unknown = await response.json();
            if (!isCurrentIdentity(user)) {
                throw new CurrentSessionError(
                    CurrentSessionFailure.ProviderUnavailable,
                );
            }
            return { userId: user.id, email: user.email };
        } catch {
            throw new CurrentSessionError(
                CurrentSessionFailure.ProviderUnavailable,
            );
        }
    }

    async endCurrentSession(accessToken: string): Promise<void> {
        let response: Response;
        try {
            response = await fetch(this.logoutUrl, {
                method: 'POST',
                headers: {
                    apikey: this.publishableKey,
                    Authorization: `Bearer ${accessToken}`,
                },
                signal: AbortSignal.timeout(AUTH_TIMEOUT_MS),
            });
        } catch {
            throw new CurrentSessionError(
                CurrentSessionFailure.ProviderUnavailable,
            );
        }
        this.assertSuccessfulStatus(response, 204);
    }

    private async verifyTokenWhenAsymmetric(token: string): Promise<void> {
        let alg: string | undefined;
        try {
            alg = decodeProtectedHeader(token).alg;
        } catch {
            throw new CurrentSessionError(
                CurrentSessionFailure.InvalidAccessToken,
            );
        }
        if (alg === 'HS256') {
            return;
        }
        if (!alg || !ASYMMETRIC_ALGORITHMS.includes(alg)) {
            throw new CurrentSessionError(
                CurrentSessionFailure.InvalidAccessToken,
            );
        }
        try {
            await jwtVerify(token, this.jwks, {
                issuer: this.issuer,
                audience: 'authenticated',
                algorithms: ASYMMETRIC_ALGORITHMS,
                requiredClaims: ['sub', 'exp'],
            });
        } catch (error) {
            if (error instanceof CurrentSessionError) {
                throw error;
            }
            if (
                error instanceof errors.JWKSTimeout ||
                error instanceof errors.JWKSInvalid ||
                !(error instanceof errors.JOSEError)
            ) {
                throw new CurrentSessionError(
                    CurrentSessionFailure.ProviderUnavailable,
                );
            }
            throw new CurrentSessionError(
                CurrentSessionFailure.InvalidAccessToken,
            );
        }
    }

    private assertSuccessfulStatus(response: Response, expected: number): void {
        if (response.status === expected) {
            return;
        }
        if ([400, 401, 403].includes(response.status)) {
            throw new CurrentSessionError(
                CurrentSessionFailure.InvalidAccessToken,
            );
        }
        if (response.status === 429) {
            throw new CurrentSessionError(CurrentSessionFailure.RateLimited);
        }
        throw new CurrentSessionError(
            CurrentSessionFailure.ProviderUnavailable,
        );
    }
}

function isCurrentIdentity(
    value: unknown,
): value is { id: string; email: string } {
    if (typeof value !== 'object' || value === null) {
        return false;
    }
    const user = value as Record<string, unknown>;
    return (
        typeof user.id === 'string' &&
        user.id.length > 0 &&
        typeof user.email === 'string' &&
        user.email.length > 0
    );
}
