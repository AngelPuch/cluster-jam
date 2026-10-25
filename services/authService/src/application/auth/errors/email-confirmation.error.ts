export enum EmailConfirmationFailure {
    InvalidCode = 'INVALID_EMAIL_CONFIRMATION_CODE',
    NotAllowed = 'EMAIL_CONFIRMATION_NOT_ALLOWED',
    RateLimited = 'RATE_LIMITED',
    ProviderUnavailable = 'PROVIDER_UNAVAILABLE',
}

export class EmailConfirmationError extends Error {
    constructor(public readonly failure: EmailConfirmationFailure) {
        super(failure);
        this.name = 'EmailConfirmationError';
    }
}
