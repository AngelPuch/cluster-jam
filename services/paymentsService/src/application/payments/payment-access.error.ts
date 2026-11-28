export class PaymentNotFound extends Error {
    constructor() {
        super('PAYMENT_NOT_FOUND');
    }
}
export class PaymentNotPayable extends Error {
    constructor() {
        super('PAYMENT_NOT_PAYABLE');
    }
}
export class InvalidPaymentToken extends Error {
    constructor() {
        super('INVALID_PAYMENT_TOKEN');
    }
}
export class PaymentKeysUnavailable extends Error {
    constructor() {
        super('PAYMENT_KEYS_UNAVAILABLE');
    }
}
