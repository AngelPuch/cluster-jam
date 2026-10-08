export enum PasswordRecoveryFailure {
    InvalidRecoveryCode = 'INVALID_RECOVERY_CODE',
    WeakPassword = 'WEAK_PASSWORD',
    SamePassword = 'SAME_PASSWORD',
    RecoveryNotAllowed = 'PASSWORD_RECOVERY_NOT_ALLOWED',
    InvalidRequest = 'INVALID_REQUEST',
    RateLimited = 'RATE_LIMITED',
    ProviderUnavailable = 'PROVIDER_UNAVAILABLE',
}

export class PasswordRecoveryError extends Error {
    constructor(public readonly failure: PasswordRecoveryFailure) {
        super(failure);
        this.name = 'PasswordRecoveryError';
    }
}
