import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { createClient } from '@supabase/supabase-js';
import { Logger } from '@nestjs/common';

import {
    AuthLoginError,
    AuthLoginFailure,
} from '../../application/auth/errors/auth-login.error';
import {
    AuthRefreshError,
    AuthRefreshFailure,
} from '../../application/auth/errors/auth-refresh.error';
import {
    AuthRegistrationError,
    AuthRegistrationFailure,
} from '../../application/auth/errors/auth-registration.error';
import {
    PasswordRecoveryError,
    PasswordRecoveryFailure,
} from '../../application/auth/errors/password-recovery.error';
import {
    type RecoverPasswordInput,
    type AuthProviderPort,
    type LoginUserInput,
    type LoginUserResult,
    type RefreshSessionInput,
    type RefreshSessionResult,
    type RegisterUserInput,
    type RegisterUserResult,
    UserRegistrationStatus,
} from '../../application/ports/auth-provider.port';

const SUPABASE_HEALTH_TIMEOUT_MS = 2_000;
const SUPABASE_REFRESH_TIMEOUT_MS = 5_000;
const SUPABASE_RECOVERY_TIMEOUT_MS = 5_000;

const noSessionStorage = {
    getItem: () => null,
    setItem: () => undefined,
    removeItem: () => undefined,
};

@Injectable()
export class SupabaseAuthAdapter implements AuthProviderPort {
    private readonly logger = new Logger(SupabaseAuthAdapter.name);
    private readonly recoveryRequestUrl: string;
    private readonly recoveryVerifyUrl: string;
    private readonly recoveryUserUrl: string;
    private readonly recoveryLogoutUrl: string;
    private readonly client: ReturnType<typeof createClient>;
    private readonly healthUrl: string;
    private readonly refreshUrl: string;
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
                persistSession: true,
                detectSessionInUrl: false,
                storage: noSessionStorage,
            },
        });

        this.healthUrl = new URL('/auth/v1/health', supabaseUrl).toString();
        this.refreshUrl = new URL(
            '/auth/v1/token?grant_type=refresh_token',
            supabaseUrl,
        ).toString();

        this.recoveryRequestUrl = new URL(
            '/auth/v1/recover',
            supabaseUrl,
        ).toString();
        this.recoveryVerifyUrl = new URL(
            '/auth/v1/verify',
            supabaseUrl,
        ).toString();
        this.recoveryUserUrl = new URL('/auth/v1/user', supabaseUrl).toString();
        this.recoveryLogoutUrl = new URL(
            '/auth/v1/logout?scope=local',
            supabaseUrl,
        ).toString();
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

    async loginUser(input: LoginUserInput): Promise<LoginUserResult> {
        try {
            const { data, error } = await this.client.auth.signInWithPassword({
                email: input.email,
                password: input.password,
            });

            if (error) {
                throw mapSupabaseLoginError(error);
            }

            if (!data.user || !data.session) {
                throw new AuthLoginError(AuthLoginFailure.ProviderUnavailable);
            }

            return {
                userId: data.user.id,
                email: data.user.email ?? input.email,
                accessToken: data.session.access_token,
                refreshToken: data.session.refresh_token,
                expiresIn: data.session.expires_in,
                tokenType: data.session.token_type,
            };
        } catch (error) {
            if (error instanceof AuthLoginError) {
                throw error;
            }

            throw new AuthLoginError(AuthLoginFailure.ProviderUnavailable);
        }
    }

    async refreshSession(
        input: RefreshSessionInput,
    ): Promise<RefreshSessionResult> {
        try {
            const response = await fetch(this.refreshUrl, {
                method: 'POST',
                headers: {
                    apikey: this.publishableKey,
                    'Content-Type': 'application/json',
                    Accept: 'application/json',
                },
                body: JSON.stringify({
                    refresh_token: input.refreshToken,
                }),
                signal: AbortSignal.timeout(SUPABASE_REFRESH_TIMEOUT_MS),
            });

            const payload: unknown = await response.json();

            if (!response.ok) {
                throw mapSupabaseRefreshError(response.status, payload);
            }

            if (!isRefreshResponse(payload)) {
                throw new AuthRefreshError(
                    AuthRefreshFailure.ProviderUnavailable,
                );
            }

            return {
                userId: payload.user.id,
                email: payload.user.email,
                accessToken: payload.access_token,
                refreshToken: payload.refresh_token,
                expiresIn: payload.expires_in,
                tokenType: payload.token_type,
            };
        } catch (error) {
            if (error instanceof AuthRefreshError) {
                throw error;
            }

            throw new AuthRefreshError(AuthRefreshFailure.ProviderUnavailable);
        }
    }

    async requestPasswordRecovery(email: string): Promise<void> {
        try {
            const response = await fetch(this.recoveryRequestUrl, {
                method: 'POST',
                headers: this.recoveryHeaders(),
                body: JSON.stringify({ email }),
                signal: AbortSignal.timeout(SUPABASE_RECOVERY_TIMEOUT_MS),
            });
            if (!response.ok) {
                this.logger.warn('Password recovery email dispatch failed.');
            }
        } catch {
            this.logger.warn('Password recovery email dispatch failed.');
        }
    }

    async recoverPassword(input: RecoverPasswordInput): Promise<void> {
        let accessToken: string | undefined;

        try {
            const verification = await fetch(this.recoveryVerifyUrl, {
                method: 'POST',
                headers: this.recoveryHeaders(),
                body: JSON.stringify({
                    email: input.email,
                    token: input.code,
                    type: 'recovery',
                }),
                signal: AbortSignal.timeout(SUPABASE_RECOVERY_TIMEOUT_MS),
            });

            if (verification.status !== 200) {
                throw await mapRecoveryResponse(verification, 'verify');
            }

            const session: unknown = await verification.json();
            if (!isRecoverySession(session)) {
                throw new PasswordRecoveryError(
                    PasswordRecoveryFailure.ProviderUnavailable,
                );
            }

            accessToken = session.access_token;
            const update = await fetch(this.recoveryUserUrl, {
                method: 'PUT',
                headers: this.recoveryHeaders(accessToken),
                body: JSON.stringify({ password: input.newPassword }),
                signal: AbortSignal.timeout(SUPABASE_RECOVERY_TIMEOUT_MS),
            });

            if (update.status !== 200) {
                throw await mapRecoveryResponse(update, 'update');
            }

            const user: unknown = await update.json();
            if (!isRecord(user) || user.id !== session.user.id) {
                throw new PasswordRecoveryError(
                    PasswordRecoveryFailure.ProviderUnavailable,
                );
            }
        } catch (error) {
            if (error instanceof PasswordRecoveryError) {
                throw error;
            }
            throw new PasswordRecoveryError(
                PasswordRecoveryFailure.ProviderUnavailable,
            );
        } finally {
            if (accessToken) {
                await this.closeRecoverySession(accessToken);
            }
        }
    }

    private recoveryHeaders(accessToken?: string): Record<string, string> {
        return {
            apikey: this.publishableKey,
            'Content-Type': 'application/json',
            Accept: 'application/json',
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        };
    }

    private async closeRecoverySession(accessToken: string): Promise<void> {
        try {
            const response = await fetch(this.recoveryLogoutUrl, {
                method: 'POST',
                headers: this.recoveryHeaders(accessToken),
                signal: AbortSignal.timeout(SUPABASE_RECOVERY_TIMEOUT_MS),
            });
            if (!response.ok) {
                this.logger.warn('Temporary recovery session cleanup failed.');
            }
        } catch {
            this.logger.warn('Temporary recovery session cleanup failed.');
        }
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

function mapSupabaseLoginError(error: { code?: string }): AuthLoginError {
    switch (error.code) {
        case 'invalid_credentials':
        case 'user_not_found':
        case 'user_banned':
            return new AuthLoginError(AuthLoginFailure.InvalidCredentials);

        case 'email_not_confirmed':
            return new AuthLoginError(AuthLoginFailure.EmailNotConfirmed);

        case 'email_address_invalid':
        case 'validation_failed':
            return new AuthLoginError(AuthLoginFailure.InvalidRequest);

        case 'over_request_rate_limit':
            return new AuthLoginError(AuthLoginFailure.RateLimited);

        case 'email_provider_disabled':
        case 'request_timeout':
        case 'unexpected_failure':
            return new AuthLoginError(AuthLoginFailure.ProviderUnavailable);

        default:
            return new AuthLoginError(AuthLoginFailure.ProviderUnavailable);
    }
}

function mapSupabaseRefreshError(
    status: number,
    payload: unknown,
): AuthRefreshError {
    const code =
        isRecord(payload) && typeof payload.error_code === 'string'
            ? payload.error_code
            : undefined;

    switch (code) {
        case 'refresh_token_not_found':
        case 'refresh_token_already_used':
        case 'session_not_found':
        case 'session_expired':
        case 'invalid_credentials':
        case 'user_not_found':
        case 'user_banned':
        case 'validation_failed':
            return new AuthRefreshError(AuthRefreshFailure.InvalidRefreshToken);

        case 'bad_json':
            return new AuthRefreshError(AuthRefreshFailure.InvalidRequest);

        case 'conflict':
            return new AuthRefreshError(AuthRefreshFailure.ConcurrentRefresh);

        case 'over_request_rate_limit':
            return new AuthRefreshError(AuthRefreshFailure.RateLimited);
    }

    if (status === 429) {
        return new AuthRefreshError(AuthRefreshFailure.RateLimited);
    }

    return new AuthRefreshError(AuthRefreshFailure.ProviderUnavailable);
}

function isRefreshResponse(value: unknown): value is {
    user: { id: string; email: string };
    access_token: string;
    refresh_token: string;
    expires_in: number;
    token_type: string;
} {
    if (!isRecord(value) || !isRecord(value.user)) {
        return false;
    }

    return (
        isNonEmptyString(value.user.id) &&
        isNonEmptyString(value.user.email) &&
        isNonEmptyString(value.access_token) &&
        isNonEmptyString(value.refresh_token) &&
        typeof value.expires_in === 'number' &&
        Number.isFinite(value.expires_in) &&
        value.expires_in > 0 &&
        isNonEmptyString(value.token_type)
    );
}

function isNonEmptyString(value: unknown): value is string {
    return typeof value === 'string' && value.length > 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}

async function mapRecoveryResponse(
    response: Response,
    stage: 'verify' | 'update',
): Promise<PasswordRecoveryError> {
    let payload: unknown;
    try {
        payload = await response.json();
    } catch {
        payload = null;
    }
    const code = isRecord(payload)
        ? typeof payload.code === 'string'
            ? payload.code
            : payload.error_code
        : undefined;

    if (response.status >= 500) {
        return new PasswordRecoveryError(
            PasswordRecoveryFailure.ProviderUnavailable,
        );
    }
    if (response.status === 429 || code === 'over_request_rate_limit') {
        return new PasswordRecoveryError(PasswordRecoveryFailure.RateLimited);
    }

    switch (code) {
        case 'otp_expired':
        case 'invalid_credentials':
        case 'session_not_found':
        case 'session_expired':
        case 'user_not_found':
        case 'bad_jwt':
            return new PasswordRecoveryError(
                PasswordRecoveryFailure.InvalidRecoveryCode,
            );
        case 'weak_password':
            return new PasswordRecoveryError(
                PasswordRecoveryFailure.WeakPassword,
            );
        case 'same_password':
            return new PasswordRecoveryError(
                PasswordRecoveryFailure.SamePassword,
            );
        case 'reauthentication_needed':
        case 'reauthentication_not_valid':
        case 'insufficient_aal':
        case 'user_banned':
            return new PasswordRecoveryError(
                PasswordRecoveryFailure.RecoveryNotAllowed,
            );
        case 'validation_failed':
            return new PasswordRecoveryError(
                stage === 'verify'
                    ? PasswordRecoveryFailure.InvalidRecoveryCode
                    : PasswordRecoveryFailure.InvalidRequest,
            );
        case 'otp_disabled':
        case 'email_provider_disabled':
            return new PasswordRecoveryError(
                PasswordRecoveryFailure.ProviderUnavailable,
            );
    }

    if (
        (stage === 'verify' && [400, 401, 403].includes(response.status)) ||
        (stage === 'update' && response.status === 401)
    ) {
        return new PasswordRecoveryError(
            PasswordRecoveryFailure.InvalidRecoveryCode,
        );
    }

    return new PasswordRecoveryError(
        PasswordRecoveryFailure.ProviderUnavailable,
    );
}

function isRecoverySession(
    value: unknown,
): value is { access_token: string; user: { id: string } } {
    return (
        isRecord(value) &&
        typeof value.access_token === 'string' &&
        value.access_token.length > 0 &&
        isRecord(value.user) &&
        typeof value.user.id === 'string' &&
        value.user.id.length > 0
    );
}
