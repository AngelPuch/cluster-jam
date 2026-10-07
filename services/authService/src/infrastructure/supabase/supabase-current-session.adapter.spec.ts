import { ConfigService } from '@nestjs/config';
import {
    afterEach,
    beforeEach,
    describe,
    expect,
    it,
    jest,
} from '@jest/globals';
import { exportJWK, generateKeyPair, SignJWT } from 'jose';

import { CurrentSessionFailure } from '../../application/auth/errors/current-session.error';
import { SupabaseCurrentSessionAdapter } from './supabase-current-session.adapter';

const config = {
    getOrThrow: (key: string): string => {
        const values: Record<string, string> = {
            SUPABASE_URL: 'https://test-project.supabase.co',
            SUPABASE_PUBLISHABLE_KEY: 'test-publishable-key',
            SUPABASE_JWKS_URL:
                'https://test-project.supabase.co/auth/v1/.well-known/jwks.json',
        };
        return values[key];
    },
} as ConfigService;

// A structurally valid HS256 token; Auth verifies its signature over HTTP.
const token = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature';
const user = {
    id: '11111111-1111-4111-8111-111111111111',
    email: 'user@example.com',
};

describe('SupabaseCurrentSessionAdapter', () => {
    let fetchSpy: jest.SpiedFunction<typeof fetch>;
    let adapter: SupabaseCurrentSessionAdapter;

    beforeEach(() => {
        fetchSpy = jest.spyOn(globalThis, 'fetch');
        adapter = new SupabaseCurrentSessionAdapter(config);
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    it('checks HS256 with Supabase and returns its user identity', async () => {
        fetchSpy.mockResolvedValue(jsonResponse(200, user));
        await expect(adapter.getCurrentIdentity(token)).resolves.toEqual({
            userId: user.id,
            email: user.email,
        });
        expect(fetchSpy).toHaveBeenCalledWith(
            'https://test-project.supabase.co/auth/v1/user',
            expect.objectContaining({
                method: 'GET',
                headers: {
                    apikey: 'test-publishable-key',
                    Authorization: `Bearer ${token}`,
                    Accept: 'application/json',
                },
            }),
        );
    });

    it('rejects malformed or revoked tokens', async () => {
        await expect(
            adapter.getCurrentIdentity('not-a-jwt'),
        ).rejects.toMatchObject({
            failure: CurrentSessionFailure.InvalidAccessToken,
        });
        expect(fetchSpy).not.toHaveBeenCalled();
        fetchSpy.mockResolvedValue(jsonResponse(401, {}));
        await expect(adapter.getCurrentIdentity(token)).rejects.toMatchObject({
            failure: CurrentSessionFailure.InvalidAccessToken,
        });
    });

    it('reports provider failure for network errors and malformed user data', async () => {
        fetchSpy.mockRejectedValueOnce(new Error('network'));
        fetchSpy.mockResolvedValueOnce(jsonResponse(200, { id: user.id }));
        await expect(adapter.getCurrentIdentity(token)).rejects.toMatchObject({
            failure: CurrentSessionFailure.ProviderUnavailable,
        });
        await expect(adapter.getCurrentIdentity(token)).rejects.toMatchObject({
            failure: CurrentSessionFailure.ProviderUnavailable,
        });
    });

    it('verifies asymmetric tokens against JWKS before checking the live session', async () => {
        const pair = await generateKeyPair('ES256');
        const key = {
            ...(await exportJWK(pair.publicKey)),
            kid: 'test-key',
            alg: 'ES256',
        };
        const jwt = await new SignJWT({ role: 'authenticated' })
            .setProtectedHeader({ alg: 'ES256', kid: 'test-key' })
            .setIssuer('https://test-project.supabase.co/auth/v1')
            .setAudience('authenticated')
            .setSubject(user.id)
            .setIssuedAt()
            .setExpirationTime('5m')
            .sign(pair.privateKey);
        fetchSpy.mockImplementation((input) => {
            const url =
                typeof input === 'string'
                    ? input
                    : input instanceof URL
                      ? input.href
                      : input.url;
            if (url.endsWith('/.well-known/jwks.json')) {
                return Promise.resolve(jsonResponse(200, { keys: [key] }));
            }
            return Promise.resolve(jsonResponse(200, user));
        });
        await expect(adapter.getCurrentIdentity(jwt)).resolves.toEqual({
            userId: user.id,
            email: user.email,
        });
        expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it('rejects an expired asymmetric token before calling /user', async () => {
        const pair = await generateKeyPair('ES256');
        const key = {
            ...(await exportJWK(pair.publicKey)),
            kid: 'test-key',
            alg: 'ES256',
        };
        const jwt = await new SignJWT({})
            .setProtectedHeader({ alg: 'ES256', kid: 'test-key' })
            .setIssuer('https://test-project.supabase.co/auth/v1')
            .setAudience('authenticated')
            .setSubject(user.id)
            .setIssuedAt()
            .setExpirationTime(Math.floor(Date.now() / 1000) - 30)
            .sign(pair.privateKey);
        fetchSpy.mockResolvedValue(jsonResponse(200, { keys: [key] }));
        await expect(adapter.getCurrentIdentity(jwt)).rejects.toMatchObject({
            failure: CurrentSessionFailure.InvalidAccessToken,
        });
        expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    it('revokes only the local session with the presented token', async () => {
        fetchSpy.mockResolvedValue(new Response(null, { status: 204 }));
        await expect(adapter.endCurrentSession(token)).resolves.toBeUndefined();
        expect(fetchSpy).toHaveBeenCalledWith(
            'https://test-project.supabase.co/auth/v1/logout?scope=local',
            expect.objectContaining({
                method: 'POST',
                headers: {
                    apikey: 'test-publishable-key',
                    Authorization: `Bearer ${token}`,
                },
            }),
        );
    });

    it('maps invalid access, rate limits and outages on logout', async () => {
        for (const [status, failure] of [
            [401, CurrentSessionFailure.InvalidAccessToken],
            [429, CurrentSessionFailure.RateLimited],
            [503, CurrentSessionFailure.ProviderUnavailable],
        ] as const) {
            fetchSpy.mockResolvedValueOnce(jsonResponse(status, {}));
            await expect(
                adapter.endCurrentSession(token),
            ).rejects.toMatchObject({
                failure,
            });
        }
    });
});

function jsonResponse(status: number, body: unknown): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}
