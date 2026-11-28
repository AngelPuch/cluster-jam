import type { StripePaymentReference } from './cancel-payment.port';
import type { PaymentStatus } from '../payments/payment';
export const OWNED_PAYMENT_STORE = Symbol('OWNED_PAYMENT_STORE');
export const PAYMENT_ACCESS_GATEWAY = Symbol('PAYMENT_ACCESS_GATEWAY');
export const PAYMENT_TOKEN_VERIFIER = Symbol('PAYMENT_TOKEN_VERIFIER');
export interface OwnedPayment {
    paymentId: string;
    orderId: string;
    status: PaymentStatus;
    amountCents: number;
    currency: 'MXN';
    reservationActive: boolean;
    refundStatus: string | null;
    reference: StripePaymentReference | null;
}
export interface OwnedPaymentStore {
    findOwned(paymentId: string, buyerId: string): Promise<OwnedPayment | null>;
}
export interface PaymentAccessGateway {
    clientSecret(payment: StripePaymentReference): Promise<string>;
}
export interface PaymentTokenVerifier {
    verify(token: string): Promise<string>;
}
