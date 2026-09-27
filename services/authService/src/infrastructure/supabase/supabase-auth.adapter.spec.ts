import { ConfigService } from '@nestjs/config';
import { type AuthError, type Session, type User } from '@supabase/supabase-js';
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
import { SupabaseAuthAdapter } from './supabase-auth.adapter';

interface AuthClientForTest {
    auth: {
        signUp(credentials: { email: string; password: string }): Promise<{
            data: {
                user: User | null;
                session: Session | null;
            };
            error: AuthError | null;
        }>;
    };
}

describe('SupabaseAuthAdapter', () => {
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
        jest.clearAllMocks();

        fetchSpy = jest.spyOn(globalThis, 'fetch');
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    it('should report Supabase Auth as available', async () => {
        fetchSpy.mockResolvedValue(
            new Response(null, {
                status: 200,
            }),
        );

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(adapter.isAvailable()).resolves.toBe(true);

        expect(fetchSpy).toHaveBeenCalledWith(
            'https://test-project.supabase.co/auth/v1/health',
            expect.objectContaining({
                method: 'GET',
                headers: {
                    apikey: 'test-publishable-key',
                },
                signal: expect.any(AbortSignal) as unknown,
            }),
        );
    });

    it('should report Supabase Auth as unavailable for non-success responses', async () => {
        fetchSpy.mockResolvedValue(
            new Response(null, {
                status: 503,
            }),
        );

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(adapter.isAvailable()).resolves.toBe(false);
    });

    it('should report Supabase Auth as unavailable for network errors', async () => {
        fetchSpy.mockRejectedValue(new TypeError('Network error'));

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(adapter.isAvailable()).resolves.toBe(false);
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

function getSignUpSpy(adapter: SupabaseAuthAdapter) {
    const client = Reflect.get(adapter, 'client') as AuthClientForTest;

    return jest.spyOn(client.auth, 'signUp');
}

function createUser(identityCount: number): User {
    return {
        id: '11111111-1111-4111-8111-111111111111',
        email: 'user@example.com',
        identities: Array.from({ length: identityCount }, (_, index) => ({
            id: `identity-${index + 1}`,
        })),
    } as unknown as User;
}

function createAuthError(code: string, status = 400): AuthError {
    return {
        name: 'AuthApiError',
        message: code,
        status,
        code,
    } as AuthError;
}
