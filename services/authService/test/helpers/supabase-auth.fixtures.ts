import { ConfigService } from '@nestjs/config';
import { jest } from '@jest/globals';
import { type AuthError, type Session, type User } from '@supabase/supabase-js';

import { SupabaseAuthAdapter } from '../../src/infrastructure/supabase/supabase-auth.adapter';

interface AuthClientForTest {
    auth: {
        signUp(credentials: { email: string; password: string }): Promise<{
            data: { user: User | null; session: Session | null };
            error: AuthError | null;
        }>;
        signInWithPassword(credentials: {
            email: string;
            password: string;
        }): Promise<{
            data: { user: User | null; session: Session | null };
            error: AuthError | null;
        }>;
    };
}

export const configService = {
    getOrThrow: jest.fn((key: string): string => {
        const values: Record<string, string> = {
            SUPABASE_URL: 'https://test-project.supabase.co',
            SUPABASE_PUBLISHABLE_KEY: 'test-publishable-key',
        };
        return values[key];
    }),
} as unknown as ConfigService;

export function getSignUpSpy(adapter: SupabaseAuthAdapter) {
    const client = Reflect.get(adapter, 'client') as AuthClientForTest;
    return jest.spyOn(client.auth, 'signUp');
}

export function getSignInWithPasswordSpy(adapter: SupabaseAuthAdapter) {
    const client = Reflect.get(adapter, 'client') as AuthClientForTest;
    return jest.spyOn(client.auth, 'signInWithPassword');
}

export function createUser(identityCount: number): User {
    return {
        id: '11111111-1111-4111-8111-111111111111',
        email: 'user@example.com',
        identities: Array.from({ length: identityCount }, (_, index) => ({
            id: `identity-${index + 1}`,
        })),
    } as unknown as User;
}

export function createAuthError(code: string, status = 400): AuthError {
    return {
        name: 'AuthApiError',
        message: code,
        status,
        code,
    } as AuthError;
}

export function createSession(): Session {
    return {
        access_token: 'access-token',
        refresh_token: 'refresh-token',
        expires_in: 3600,
        token_type: 'bearer',
        user: createUser(1),
    };
}
