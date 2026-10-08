import { Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import {
    afterEach,
    beforeEach,
    describe,
    expect,
    it,
    jest,
} from '@jest/globals';

import { PasswordRecoveryFailure } from '../../application/auth/errors/password-recovery.error';
import { SupabaseAuthAdapter } from './supabase-auth.adapter';

const baseUrl = 'https://test-project.supabase.co/auth/v1';
const config = {
    getOrThrow: (key: string): string => {
        const values: Record<string, string> = {
            SUPABASE_URL: 'https://test-project.supabase.co',
            SUPABASE_PUBLISHABLE_KEY: 'test-publishable-key',
        };
        return values[key];
    },
} as ConfigService;

const input = {
    email: 'user@example.com',
    code: '012345',
    newPassword: ' NewStrongPassword123! ',
};
const user = { id: '11111111-1111-4111-8111-111111111111' };
const verifiedSession = {
    access_token: 'recovery-access-token',
    refresh_token: 'recovery-refresh-token',
    user,
};

describe('SupabaseAuthAdapter', () => {
    let adapter: SupabaseAuthAdapter;
    let fetchSpy: jest.SpiedFunction<typeof fetch>;
    let warnSpy: jest.SpiedFunction<Logger['warn']>;

    beforeEach(() => {
        fetchSpy = jest.spyOn(globalThis, 'fetch');
        warnSpy = jest
            .spyOn(Logger.prototype, 'warn')
            .mockImplementation(() => {});
        adapter = new SupabaseAuthAdapter(config);
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    it('sends only email without redirect parameters to Supabase', async () => {
        fetchSpy.mockResolvedValue(jsonResponse(200, {}));
        await expect(
            adapter.requestPasswordRecovery('user@example.com'),
        ).resolves.toBeUndefined();
        const [url, options] = fetchSpy.mock.calls[0];
        expect(requestUrl(url)).toBe(`${baseUrl}/recover`);
        expect(new URL(requestUrl(url)).search).toBe('');
        expect(options).toMatchObject({
            method: 'POST',
            body: JSON.stringify({ email: 'user@example.com' }),
            headers: { apikey: 'test-publishable-key' },
            signal: expect.any(AbortSignal),
        });
        expect(options?.headers).not.toHaveProperty('Authorization');
    });

    it.each([400, 404, 422, 429, 500, 503])(
        'keeps email dispatch errors neutral, including HTTP %s',
        async (status) => {
            fetchSpy.mockResolvedValue(
                jsonResponse(status, {
                    error_code: 'email_address_not_authorized',
                    msg: 'user@example.com private provider message',
                }),
            );
            await expect(
                adapter.requestPasswordRecovery('user@example.com'),
            ).resolves.toBeUndefined();
            expect(warnSpy).toHaveBeenCalledWith(
                'Password recovery email dispatch failed.',
            );
        },
    );

    it('keeps network errors neutral and logs no private details', async () => {
        fetchSpy.mockRejectedValue(new Error('user@example.com secret'));
        await expect(
            adapter.requestPasswordRecovery('user@example.com'),
        ).resolves.toBeUndefined();
        expect(JSON.stringify(warnSpy.mock.calls)).not.toContain('secret');
        expect(JSON.stringify(warnSpy.mock.calls)).not.toContain(
            'user@example.com',
        );
    });

    it('verifies recovery before updating, then closes only the temporary session', async () => {
        fetchSpy
            .mockResolvedValueOnce(jsonResponse(200, verifiedSession))
            .mockResolvedValueOnce(jsonResponse(200, user))
            .mockResolvedValueOnce(new Response(null, { status: 204 }));
        await expect(adapter.recoverPassword(input)).resolves.toBeUndefined();
        expect(fetchSpy.mock.calls.map(([url]) => url)).toEqual([
            `${baseUrl}/verify`,
            `${baseUrl}/user`,
            `${baseUrl}/logout?scope=local`,
        ]);
        expect(fetchSpy.mock.calls[0][1]).toMatchObject({
            method: 'POST',
            body: JSON.stringify({
                email: input.email,
                token: input.code,
                type: 'recovery',
            }),
        });
        expect(fetchSpy.mock.calls[1][1]).toMatchObject({
            method: 'PUT',
            headers: { Authorization: 'Bearer recovery-access-token' },
            body: JSON.stringify({ password: input.newPassword }),
        });
        expect(fetchSpy.mock.calls[2][1]).toMatchObject({
            method: 'POST',
            headers: { Authorization: 'Bearer recovery-access-token' },
        });
        const storedStrings = Object.values(adapter).filter(
            (value): value is string => typeof value === 'string',
        );
        for (const secret of [
            input.email,
            input.code,
            input.newPassword,
            verifiedSession.access_token,
            verifiedSession.refresh_token,
        ]) {
            expect(storedStrings).not.toContain(secret);
        }
    });

    it.each([
        [403, 'otp_expired', PasswordRecoveryFailure.InvalidRecoveryCode],
        [400, 'validation_failed', PasswordRecoveryFailure.InvalidRecoveryCode],
        [429, 'over_request_rate_limit', PasswordRecoveryFailure.RateLimited],
        [
            500,
            'unexpected_failure',
            PasswordRecoveryFailure.ProviderUnavailable,
        ],
        [403, 'otp_disabled', PasswordRecoveryFailure.ProviderUnavailable],
    ] as const)(
        'maps verify error %s/%s and never updates',
        async (status, code, failure) => {
            fetchSpy.mockResolvedValue(
                jsonResponse(status, { error_code: code }),
            );
            await expect(adapter.recoverPassword(input)).rejects.toMatchObject({
                failure,
            });
            expect(fetchSpy).toHaveBeenCalledTimes(1);
        },
    );

    it.each([
        [422, 'weak_password', PasswordRecoveryFailure.WeakPassword],
        [422, 'same_password', PasswordRecoveryFailure.SamePassword],
        [
            403,
            'reauthentication_needed',
            PasswordRecoveryFailure.RecoveryNotAllowed,
        ],
        [403, 'insufficient_aal', PasswordRecoveryFailure.RecoveryNotAllowed],
        [422, 'validation_failed', PasswordRecoveryFailure.InvalidRequest],
        [401, 'session_not_found', PasswordRecoveryFailure.InvalidRecoveryCode],
        [429, 'over_request_rate_limit', PasswordRecoveryFailure.RateLimited],
        [
            503,
            'unexpected_failure',
            PasswordRecoveryFailure.ProviderUnavailable,
        ],
    ] as const)(
        'maps update error %s/%s and cleans the consumed session',
        async (status, code, failure) => {
            fetchSpy
                .mockResolvedValueOnce(jsonResponse(200, verifiedSession))
                .mockResolvedValueOnce(
                    jsonResponse(status, { code, msg: 'private details' }),
                )
                .mockResolvedValueOnce(new Response(null, { status: 204 }));
            await expect(adapter.recoverPassword(input)).rejects.toMatchObject({
                failure,
                message: failure,
            });
            expect(fetchSpy).toHaveBeenCalledTimes(3);
        },
    );

    it.each([{}, { access_token: 'token' }, { access_token: '', user }])(
        'rejects a malformed verification response',
        async (payload) => {
            fetchSpy.mockResolvedValue(jsonResponse(200, payload));
            await expect(adapter.recoverPassword(input)).rejects.toMatchObject({
                failure: PasswordRecoveryFailure.ProviderUnavailable,
            });
            expect(fetchSpy).toHaveBeenCalledTimes(1);
        },
    );

    it('rejects a mismatched user in the update response', async () => {
        fetchSpy
            .mockResolvedValueOnce(jsonResponse(200, verifiedSession))
            .mockResolvedValueOnce(jsonResponse(200, { id: 'different-user' }))
            .mockResolvedValueOnce(new Response(null, { status: 204 }));
        await expect(adapter.recoverPassword(input)).rejects.toMatchObject({
            failure: PasswordRecoveryFailure.ProviderUnavailable,
        });
    });

    it('maps network failures before verification to provider unavailability', async () => {
        fetchSpy.mockRejectedValue(new Error('private network error'));
        await expect(adapter.recoverPassword(input)).rejects.toMatchObject({
            failure: PasswordRecoveryFailure.ProviderUnavailable,
        });
        expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    it('cleans up after a failed update transport', async () => {
        fetchSpy
            .mockResolvedValueOnce(jsonResponse(200, verifiedSession))
            .mockRejectedValueOnce(new Error('network'))
            .mockResolvedValueOnce(new Response(null, { status: 204 }));
        await expect(adapter.recoverPassword(input)).rejects.toMatchObject({
            failure: PasswordRecoveryFailure.ProviderUnavailable,
        });
        expect(fetchSpy).toHaveBeenCalledTimes(3);
    });

    it.each(['http', 'network'])(
        'does not report a failed update when cleanup fails via %s',
        async (failure) => {
            fetchSpy
                .mockResolvedValueOnce(jsonResponse(200, verifiedSession))
                .mockResolvedValueOnce(jsonResponse(200, user));
            if (failure === 'http') {
                fetchSpy.mockResolvedValueOnce(jsonResponse(503, {}));
            } else {
                fetchSpy.mockRejectedValueOnce(
                    new Error('private token details'),
                );
            }
            await expect(
                adapter.recoverPassword(input),
            ).resolves.toBeUndefined();
            expect(warnSpy).toHaveBeenCalledWith(
                'Temporary recovery session cleanup failed.',
            );
        },
    );

    it('keeps concurrent users tokens separate', async () => {
        fetchSpy.mockImplementation((url, options) => {
            const body =
                typeof options?.body === 'string'
                    ? (JSON.parse(options.body) as Record<string, string>)
                    : {};
            if (requestUrl(url).endsWith('/verify')) {
                expect(body.type).toBe('recovery');
                expect(body.token).toBe(
                    body.email === 'alice@example.com' ? '012345' : '654321',
                );
                return Promise.resolve(
                    jsonResponse(200, {
                        access_token: `access-${body.email}`,
                        user: { id: body.email },
                    }),
                );
            }
            const headers = options?.headers as Record<string, string>;
            const id = headers.Authorization.replace('Bearer access-', '');
            if (requestUrl(url).endsWith('/user')) {
                expect(body.password).toBe(`PasswordFor-${id}`);
                return Promise.resolve(jsonResponse(200, { id }));
            }
            return Promise.resolve(new Response(null, { status: 204 }));
        });
        await Promise.all([
            adapter.recoverPassword({
                email: 'alice@example.com',
                code: '012345',
                newPassword: 'PasswordFor-alice@example.com',
            }),
            adapter.recoverPassword({
                email: 'bob@example.com',
                code: '654321',
                newPassword: 'PasswordFor-bob@example.com',
            }),
        ]);
        expect(fetchSpy).toHaveBeenCalledTimes(6);
    });
});

function jsonResponse(status: number, body: unknown): Response {
    return new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
    });
}

function requestUrl(input: Parameters<typeof fetch>[0]): string {
    if (typeof input === 'string') {
        return input;
    }
    return input instanceof URL ? input.href : input.url;
}
