import type { RefundPayment } from '../payments/payment-messages';
import type { StripePaymentReference } from './cancel-payment.port';
import type { StripePaymentSnapshot } from './payment-notice.port';
export const REFUND_PAYMENT_STORE = Symbol('REFUND_PAYMENT_STORE');
export const REFUND_GATEWAY = Symbol('REFUND_GATEWAY');
export const REFUND_NOTICE_STORE = Symbol('REFUND_NOTICE_STORE');
export interface PreparedRefund {
    id: string;
    payment: StripePaymentReference;
    stripeRefundId: string | null;
    creationAgeMs: number;
}
export interface RefundSnapshot {
    id: string;
    refundId: string;
    payment: StripePaymentSnapshot;
    status: string;
}
export interface RefundPaymentStore {
    prepare(command: RefundPayment): Promise<PreparedRefund | null>;
    complete(command: RefundPayment, refund: RefundSnapshot): Promise<void>;
}
export interface RefundGateway {
    ensure(refund: PreparedRefund): Promise<RefundSnapshot>;
    read(id: string): Promise<RefundSnapshot | null>;
}
export interface RefundNotice {
    eventId: string;
    refundId: string;
}
export interface RefundNoticeStore {
    processed(eventId: string): Promise<boolean>;
    apply(eventId: string, refund: RefundSnapshot): Promise<void>;
}
