import {
    afterEach,
    beforeEach,
    describe,
    expect,
    it,
    jest,
} from '@jest/globals';

import { AuthLoginFailure } from '../../application/auth/errors/auth-login.error';
import {
    configService,
    createAuthError,
    createSession,
    createUser,
    getSignInWithPasswordSpy,
} from '../../../test/helpers/supabase-auth.fixtures';
import { SupabaseAuthAdapter } from './supabase-auth.adapter';

describe('SupabaseAuthAdapter.loginUser', () => {
    beforeEach(() => {
        jest.clearAllMocks();
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    it('should login a user and return the session tokens', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signInSpy = getSignInWithPasswordSpy(adapter);

        signInSpy.mockResolvedValue({
            data: {
                user: createUser(1),
                session: createSession(),
            },
            error: null,
        });

        await expect(
            adapter.loginUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).resolves.toEqual({
            userId: '11111111-1111-4111-8111-111111111111',
            email: 'user@example.com',
            accessToken: 'access-token',
            refreshToken: 'refresh-token',
            expiresIn: 3600,
            tokenType: 'bearer',
        });

        expect(signInSpy).toHaveBeenCalledWith({
            email: 'user@example.com',
            password: 'StrongPassword123!',
        });
    });

    it('should translate invalid login credentials', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signInSpy = getSignInWithPasswordSpy(adapter);

        signInSpy.mockResolvedValue({
            data: {
                user: null,
                session: null,
            },
            error: createAuthError('invalid_credentials'),
        });

        await expect(
            adapter.loginUser({
                email: 'user@example.com',
                password: 'WrongPassword!',
            }),
        ).rejects.toMatchObject({
            failure: AuthLoginFailure.InvalidCredentials,
        });
    });

    it('should translate an unconfirmed email error', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signInSpy = getSignInWithPasswordSpy(adapter);

        signInSpy.mockResolvedValue({
            data: {
                user: null,
                session: null,
            },
            error: createAuthError('email_not_confirmed'),
        });

        await expect(
            adapter.loginUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).rejects.toMatchObject({
            failure: AuthLoginFailure.EmailNotConfirmed,
        });
    });

    it('should translate invalid login data', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signInSpy = getSignInWithPasswordSpy(adapter);

        signInSpy.mockResolvedValue({
            data: {
                user: null,
                session: null,
            },
            error: createAuthError('validation_failed'),
        });

        await expect(
            adapter.loginUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).rejects.toMatchObject({
            failure: AuthLoginFailure.InvalidRequest,
        });
    });

    it('should translate a login rate limit error', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signInSpy = getSignInWithPasswordSpy(adapter);

        signInSpy.mockResolvedValue({
            data: {
                user: null,
                session: null,
            },
            error: createAuthError('over_request_rate_limit', 429),
        });

        await expect(
            adapter.loginUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).rejects.toMatchObject({
            failure: AuthLoginFailure.RateLimited,
        });
    });

    it('should translate login provider failures as unavailable', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signInSpy = getSignInWithPasswordSpy(adapter);

        signInSpy.mockResolvedValue({
            data: {
                user: null,
                session: null,
            },
            error: createAuthError('unexpected_failure', 500),
        });

        await expect(
            adapter.loginUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).rejects.toMatchObject({
            failure: AuthLoginFailure.ProviderUnavailable,
        });
    });

    it('should reject a login response without a session', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signInSpy = getSignInWithPasswordSpy(adapter);

        signInSpy.mockResolvedValue({
            data: {
                user: createUser(1),
                session: null,
            },
            error: null,
        });

        await expect(
            adapter.loginUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).rejects.toMatchObject({
            failure: AuthLoginFailure.ProviderUnavailable,
        });
    });

    it('should translate login network errors as unavailable', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signInSpy = getSignInWithPasswordSpy(adapter);

        signInSpy.mockRejectedValue(new TypeError('Network error'));

        await expect(
            adapter.loginUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).rejects.toMatchObject({
            failure: AuthLoginFailure.ProviderUnavailable,
        });
    });
});
