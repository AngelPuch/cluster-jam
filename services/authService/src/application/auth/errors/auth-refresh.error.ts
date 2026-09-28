export enum AuthRefreshFailure {
    InvalidRefreshToken = 'INVALID_REFRESH_TOKEN',
    InvalidRequest = 'INVALID_REQUEST',
    ConcurrentRefresh = 'SESSION_REFRESH_CONFLICT',
    RateLimited = 'RATE_LIMITED',
    ProviderUnavailable = 'PROVIDER_UNAVAILABLE',
}

export class AuthRefreshError extends Error {
    constructor(public readonly failure: AuthRefreshFailure) {
        super(failure);

        this.name = 'AuthRefreshError';
    }
}
