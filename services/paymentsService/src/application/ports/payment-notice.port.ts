export const PAYMENT_NOTICE_STORE = Symbol('PAYMENT_NOTICE_STORE');
export const STRIPE_PAYMENT_READER = Symbol('STRIPE_PAYMENT_READER');

export interface PaymentNotice {
    eventId: string;
    paymentIntentId: string;
}
export interface StripePaymentSnapshot {
    id: string;
    paymentId: string;
    orderId: string;
    buyerId: string;
    reservationId: string;
    amountCents: number;
    currency: 'MXN';
    status: string;
}
export interface PaymentNoticeStore {
    processed(eventId: string): Promise<boolean>;
    apply(eventId: string, payment: StripePaymentSnapshot): Promise<void>;
}
export interface StripePaymentReader {
    read(id: string): Promise<StripePaymentSnapshot | null>;
}
