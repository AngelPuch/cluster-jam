export enum AccessTokenFailure {
    InvalidAccessToken = 'INVALID_ACCESS_TOKEN',
    InvalidAppRole = 'INVALID_APP_ROLE',
    KeysUnavailable = 'SERVICE_UNAVAILABLE',
}

export class AccessTokenError extends Error {
    constructor(public readonly failure: AccessTokenFailure) {
        super(failure);
        this.name = 'AccessTokenError';
    }
}
