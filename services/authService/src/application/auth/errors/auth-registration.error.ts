export enum AuthRegistrationFailure {
    EmailAlreadyRegistered = 'EMAIL_ALREADY_REGISTERED',
    InvalidEmail = 'INVALID_EMAIL',
    InvalidRequest = 'INVALID_REQUEST',
    WeakPassword = 'WEAK_PASSWORD',
    RateLimited = 'RATE_LIMITED',
    ProviderUnavailable = 'PROVIDER_UNAVAILABLE',
}

export class AuthRegistrationError extends Error {
    constructor(public readonly failure: AuthRegistrationFailure) {
        super(failure);

        this.name = 'AuthRegistrationError';
    }
}
