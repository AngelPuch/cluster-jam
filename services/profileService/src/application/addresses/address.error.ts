export enum AddressFailure {
    InvalidInput = 'VALIDATION_ERROR',
    NotFound = 'ADDRESS_NOT_FOUND',
    RevisionMismatch = 'PRECONDITION_FAILED',
    PersistenceUnavailable = 'SERVICE_UNAVAILABLE',
}

export class AddressError extends Error {
    constructor(public readonly failure: AddressFailure) {
        super(failure);
        this.name = 'AddressError';
    }
}
