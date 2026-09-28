export enum AuthLoginFailure {
    InvalidCredentials = 'INVALID_CREDENTIALS',
    EmailNotConfirmed = 'EMAIL_NOT_CONFIRMED',
    InvalidRequest = 'INVALID_REQUEST',
    RateLimited = 'RATE_LIMITED',
    ProviderUnavailable = 'PROVIDER_UNAVAILABLE',
}

export class AuthLoginError extends Error {
    constructor(public readonly failure: AuthLoginFailure) {
        super(failure);

        this.name = 'AuthLoginError';
    }
}
