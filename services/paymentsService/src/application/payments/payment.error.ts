export class PaymentCommandConflict extends Error {
    constructor() {
        super('PAYMENT_COMMAND_CONFLICT');
    }
}
export class PaymentProviderMismatch extends Error {
    constructor() {
        super('PAYMENT_PROVIDER_MISMATCH');
    }
}
export class PaymentRecoveryRequired extends Error {
    constructor() {
        super('PAYMENT_RECOVERY_REQUIRED');
    }
}
export class PaymentProviderUnavailable extends Error {
    constructor() {
        super('PAYMENT_PROVIDER_UNAVAILABLE');
    }
}
export class PaymentPersistenceUnavailable extends Error {
    constructor() {
        super('PAYMENT_PERSISTENCE_UNAVAILABLE');
    }
}
