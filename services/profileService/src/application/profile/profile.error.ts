export enum ProfileFailure {
    NotReady = 'PROFILE_NOT_READY',
    InvalidUpdate = 'VALIDATION_ERROR',
    ContactEmailRequired = 'PROFILE_CONTACT_EMAIL_REQUIRED',
    RevisionMismatch = 'PRECONDITION_FAILED',
    PersistenceUnavailable = 'SERVICE_UNAVAILABLE',
}

export class ProfileError extends Error {
    constructor(public readonly failure: ProfileFailure) {
        super(failure);
        this.name = 'ProfileError';
    }
}
