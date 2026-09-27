import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { createClient } from '@supabase/supabase-js';

import {
    AuthRegistrationError,
    AuthRegistrationFailure,
} from '../../application/auth/errors/auth-registration.error';
import {
    type AuthProviderPort,
    type RegisterUserInput,
    type RegisterUserResult,
    UserRegistrationStatus,
} from '../../application/ports/auth-provider.port';

const SUPABASE_HEALTH_TIMEOUT_MS = 2_000;

@Injectable()
export class SupabaseAuthAdapter implements AuthProviderPort {
    private readonly client: ReturnType<typeof createClient>;
    private readonly healthUrl: string;
    private readonly publishableKey: string;

    constructor(private readonly configService: ConfigService) {
        const supabaseUrl =
            this.configService.getOrThrow<string>('SUPABASE_URL');

        this.publishableKey = this.configService.getOrThrow<string>(
            'SUPABASE_PUBLISHABLE_KEY',
        );

        this.client = createClient(supabaseUrl, this.publishableKey, {
            auth: {
                autoRefreshToken: false,
                persistSession: false,
                detectSessionInUrl: false,
            },
        });

        this.healthUrl = new URL('/auth/v1/health', supabaseUrl).toString();
    }

    async isAvailable(): Promise<boolean> {
        try {
            const response = await fetch(this.healthUrl, {
                method: 'GET',
                headers: {
                    apikey: this.publishableKey,
                },
                signal: AbortSignal.timeout(SUPABASE_HEALTH_TIMEOUT_MS),
            });

            return response.ok;
        } catch {
            return false;
        }
    }

    async registerUser(input: RegisterUserInput): Promise<RegisterUserResult> {
        const { data, error } = await this.client.auth.signUp({
            email: input.email,
            password: input.password,
        });

        if (error) {
            throw mapSupabaseRegistrationError(error);
        }

        if (!data.user) {
            throw new AuthRegistrationError(
                AuthRegistrationFailure.ProviderUnavailable,
            );
        }

        if (data.user.identities?.length === 0) {
            throw new AuthRegistrationError(
                AuthRegistrationFailure.EmailAlreadyRegistered,
            );
        }

        return {
            userId: data.user.id,
            email: data.user.email ?? input.email,
            status:
                data.session === null
                    ? UserRegistrationStatus.PendingEmailConfirmation
                    : UserRegistrationStatus.Active,
        };
    }
}

function mapSupabaseRegistrationError(error: {
    code?: string;
}): AuthRegistrationError {
    switch (error.code) {
        case 'email_exists':
        case 'user_already_exists':
            return new AuthRegistrationError(
                AuthRegistrationFailure.EmailAlreadyRegistered,
            );

        case 'email_address_invalid':
            return new AuthRegistrationError(
                AuthRegistrationFailure.InvalidEmail,
            );

        case 'validation_failed':
            return new AuthRegistrationError(
                AuthRegistrationFailure.InvalidRequest,
            );

        case 'weak_password':
            return new AuthRegistrationError(
                AuthRegistrationFailure.WeakPassword,
            );

        case 'over_email_send_rate_limit':
        case 'over_request_rate_limit':
            return new AuthRegistrationError(
                AuthRegistrationFailure.RateLimited,
            );

        case 'email_address_not_authorized':
        case 'email_provider_disabled':
        case 'signup_disabled':
        case 'request_timeout':
        case 'unexpected_failure':
            return new AuthRegistrationError(
                AuthRegistrationFailure.ProviderUnavailable,
            );

        default:
            return new AuthRegistrationError(
                AuthRegistrationFailure.ProviderUnavailable,
            );
    }
}
