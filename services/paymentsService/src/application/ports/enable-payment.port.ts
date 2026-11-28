import type { EnablePayment } from '../payments/payment-messages';

export const ENABLE_PAYMENT_STORE = Symbol('ENABLE_PAYMENT_STORE');
export const PAYMENT_INTENT_GATEWAY = Symbol('PAYMENT_INTENT_GATEWAY');

export interface PreparedPayment {
    id: string;
    orderId: string;
    buyerId: string;
    reservationId: string;
    amountCents: number;
    currency: 'MXN';
    stripePaymentIntentId: string | null;
    creationAgeMs: number;
}
export interface ProviderIntent {
    id: string;
    status: string;
}
export interface EnablePaymentStore {
    prepare(command: EnablePayment): Promise<PreparedPayment | null>;
    complete(command: EnablePayment, paymentId: string, intent: ProviderIntent): Promise<void>;
}
export interface PaymentIntentGateway {
    ensure(payment: PreparedPayment): Promise<ProviderIntent>;
}
