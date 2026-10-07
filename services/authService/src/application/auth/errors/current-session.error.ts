export enum CurrentSessionFailure {
    InvalidAccessToken = 'INVALID_ACCESS_TOKEN',
    RateLimited = 'RATE_LIMITED',
    ProviderUnavailable = 'PROVIDER_UNAVAILABLE',
}

export class CurrentSessionError extends Error {
    constructor(public readonly failure: CurrentSessionFailure) {
        super(failure);
        this.name = 'CurrentSessionError';
    }
}
