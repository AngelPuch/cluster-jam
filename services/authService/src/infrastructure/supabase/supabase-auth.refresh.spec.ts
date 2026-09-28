import { ConfigService } from '@nestjs/config';
import {
    afterEach,
    beforeEach,
    describe,
    expect,
    it,
    jest,
} from '@jest/globals';

import { AuthRefreshFailure } from '../../application/auth/errors/auth-refresh.error';
import { SupabaseAuthAdapter } from './supabase-auth.adapter';

describe('SupabaseAuthAdapter.refreshSession', () => {
    let fetchSpy: jest.SpiedFunction<typeof fetch>;

    const configService = {
        getOrThrow: jest.fn((key: string): string => {
            const values: Record<string, string> = {
                SUPABASE_URL: 'https://test-project.supabase.co',
                SUPABASE_PUBLISHABLE_KEY: 'test-publishable-key',
            };

            return values[key];
        }),
    } as unknown as ConfigService;

    beforeEach(() => {
        fetchSpy = jest.spyOn(globalThis, 'fetch');
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    it('exchanges the supplied token and returns both new tokens', async () => {
        fetchSpy.mockResolvedValue(
            jsonResponse(200, {
                user: {
                    id: '11111111-1111-4111-8111-111111111111',
                    email: 'user@example.com',
                },
                access_token: 'new-access-token',
                refresh_token: 'new-refresh-token',
                expires_in: 3600,
                token_type: 'bearer',
            }),
        );

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(
            adapter.refreshSession({
                refreshToken: 'old-refresh-token',
            }),
        ).resolves.toEqual({
            userId: '11111111-1111-4111-8111-111111111111',
            email: 'user@example.com',
            accessToken: 'new-access-token',
            refreshToken: 'new-refresh-token',
            expiresIn: 3600,
            tokenType: 'bearer',
        });

        expect(fetchSpy).toHaveBeenCalledWith(
            'https://test-project.supabase.co/auth/v1/token?grant_type=refresh_token',
            expect.objectContaining({
                method: 'POST',
                headers: {
                    apikey: 'test-publishable-key',
                    'Content-Type': 'application/json',
                    Accept: 'application/json',
                },
                body: JSON.stringify({
                    refresh_token: 'old-refresh-token',
                }),
                signal: expect.any(AbortSignal) as unknown,
            }),
        );
    });

    it('rejects a token that Supabase cannot find', async () => {
        fetchSpy.mockResolvedValue(
            jsonResponse(400, { error_code: 'refresh_token_not_found' }),
        );

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(
            adapter.refreshSession({ refreshToken: 'invalid-token' }),
        ).rejects.toMatchObject({
            failure: AuthRefreshFailure.InvalidRefreshToken,
        });
    });

    it('rejects an already used token', async () => {
        fetchSpy.mockResolvedValue(
            jsonResponse(400, { error_code: 'refresh_token_already_used' }),
        );

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(
            adapter.refreshSession({ refreshToken: 'used-token' }),
        ).rejects.toMatchObject({
            failure: AuthRefreshFailure.InvalidRefreshToken,
        });
    });

    it('maps concurrent renewal conflicts', async () => {
        fetchSpy.mockResolvedValue(
            jsonResponse(409, { error_code: 'conflict' }),
        );

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(
            adapter.refreshSession({ refreshToken: 'token' }),
        ).rejects.toMatchObject({
            failure: AuthRefreshFailure.ConcurrentRefresh,
        });
    });

    it('maps rate limiting', async () => {
        fetchSpy.mockResolvedValue(jsonResponse(429, {}));

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(
            adapter.refreshSession({ refreshToken: 'token' }),
        ).rejects.toMatchObject({
            failure: AuthRefreshFailure.RateLimited,
        });
    });

    it('rejects an incomplete success response', async () => {
        fetchSpy.mockResolvedValue(
            jsonResponse(200, { access_token: 'access-only' }),
        );

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(
            adapter.refreshSession({ refreshToken: 'token' }),
        ).rejects.toMatchObject({
            failure: AuthRefreshFailure.ProviderUnavailable,
        });
    });

    it('maps network failures without exposing the token', async () => {
        fetchSpy.mockRejectedValue(new TypeError('Network error'));

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(
            adapter.refreshSession({ refreshToken: 'secret-token' }),
        ).rejects.toMatchObject({
            failure: AuthRefreshFailure.ProviderUnavailable,
        });
    });

    it('returns invalid refresh token for a malformed token', async () => {
        fetchSpy.mockResolvedValue(
            jsonResponse(400, {
                code: 400,
                error_code: 'validation_failed',
                msg: 'Refresh token is not valid',
            }),
        );

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(
            adapter.refreshSession({ refreshToken: 'tokenno223' }),
        ).rejects.toMatchObject({
            failure: AuthRefreshFailure.InvalidRefreshToken,
        });
    });
});

function jsonResponse(status: number, body: unknown): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}
