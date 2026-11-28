export enum PaymentStatus {
    Pending = 'PENDIENTE',
    Paid = 'PAGADO',
    Cancelled = 'CANCELADO',
    Refunded = 'REEMBOLSADO',
    Failed = 'FALLIDO',
}

export function requirePositiveCents(value: unknown): number {
    if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 1) {
        throw new RangeError('Amount must be a positive safe integer in cents.');
    }
    return value;
}
