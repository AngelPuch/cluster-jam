import {
    afterEach,
    beforeEach,
    describe,
    expect,
    it,
    jest,
} from '@jest/globals';

import { AuthRegistrationFailure } from '../../application/auth/errors/auth-registration.error';
import { UserRegistrationStatus } from '../../application/ports/auth-provider.port';
import {
    configService,
    createAuthError,
    createUser,
    getSignUpSpy,
} from '../../../test/helpers/supabase-auth.fixtures';
import { SupabaseAuthAdapter } from './supabase-auth.adapter';

describe('SupabaseAuthAdapter.registerUser', () => {
    beforeEach(() => {
        jest.clearAllMocks();
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    it('should register a user pending email confirmation', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signUpSpy = getSignUpSpy(adapter);

        signUpSpy.mockResolvedValue({
            data: {
                user: createUser(1),
                session: null,
            },
            error: null,
        });

        await expect(
            adapter.registerUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).resolves.toEqual({
            userId: '11111111-1111-4111-8111-111111111111',
            email: 'user@example.com',
            status: UserRegistrationStatus.PendingEmailConfirmation,
        });

        expect(signUpSpy).toHaveBeenCalledWith({
            email: 'user@example.com',
            password: 'StrongPassword123!',
        });
    });

    it('should reject an obfuscated duplicate user response', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signUpSpy = getSignUpSpy(adapter);

        signUpSpy.mockResolvedValue({
            data: {
                user: createUser(0),
                session: null,
            },
            error: null,
        });

        await expect(
            adapter.registerUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).rejects.toMatchObject({
            failure: AuthRegistrationFailure.EmailAlreadyRegistered,
        });
    });

    it('should translate an existing user error', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signUpSpy = getSignUpSpy(adapter);

        signUpSpy.mockResolvedValue({
            data: {
                user: null,
                session: null,
            },
            error: createAuthError('user_already_exists'),
        });

        await expect(
            adapter.registerUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).rejects.toMatchObject({
            failure: AuthRegistrationFailure.EmailAlreadyRegistered,
        });
    });

    it('should translate a weak password error', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signUpSpy = getSignUpSpy(adapter);

        signUpSpy.mockResolvedValue({
            data: {
                user: null,
                session: null,
            },
            error: createAuthError('weak_password'),
        });

        await expect(
            adapter.registerUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).rejects.toMatchObject({
            failure: AuthRegistrationFailure.WeakPassword,
        });
    });

    it('should translate an invalid email error', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signUpSpy = getSignUpSpy(adapter);

        signUpSpy.mockResolvedValue({
            data: {
                user: null,
                session: null,
            },
            error: createAuthError('email_address_invalid'),
        });

        await expect(
            adapter.registerUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).rejects.toMatchObject({
            failure: AuthRegistrationFailure.InvalidEmail,
        });
    });

    it('should translate a registration rate limit error', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signUpSpy = getSignUpSpy(adapter);

        signUpSpy.mockResolvedValue({
            data: {
                user: null,
                session: null,
            },
            error: createAuthError('over_email_send_rate_limit', 429),
        });

        await expect(
            adapter.registerUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).rejects.toMatchObject({
            failure: AuthRegistrationFailure.RateLimited,
        });
    });

    it('should translate provider failures as unavailable', async () => {
        const adapter = new SupabaseAuthAdapter(configService);

        const signUpSpy = getSignUpSpy(adapter);

        signUpSpy.mockResolvedValue({
            data: {
                user: null,
                session: null,
            },
            error: createAuthError('unexpected_failure', 500),
        });

        await expect(
            adapter.registerUser({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).rejects.toMatchObject({
            failure: AuthRegistrationFailure.ProviderUnavailable,
        });
    });
});
