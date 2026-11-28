import type { CancelPayment } from '../payments/payment-messages';
import type { StripePaymentSnapshot } from './payment-notice.port';
export const CANCEL_PAYMENT_STORE = Symbol('CANCEL_PAYMENT_STORE');
export const CANCEL_PAYMENT_GATEWAY = Symbol('CANCEL_PAYMENT_GATEWAY');
export type StripePaymentReference = Omit<StripePaymentSnapshot, 'status'>;
export interface CancelPaymentStore {
    prepare(command: CancelPayment): Promise<StripePaymentReference | null>;
    complete(command: CancelPayment, intent: StripePaymentSnapshot): Promise<void>;
}
export interface CancelPaymentGateway {
    cancel(payment: StripePaymentReference): Promise<StripePaymentSnapshot>;
}
