export enum PaymentMessageType {
    Enable = 'cmd.payments.enable-payment.v1',
    Cancel = 'cmd.payments.cancel-payment.v1',
    Refund = 'cmd.payments.refund-full.v1',
    Enabled = 'payments.payment.enabled.v1',
    Succeeded = 'payments.payment.succeeded.v1',
    NotCompleted = 'payments.payment.not-completed.v1',
    RefundSucceeded = 'payments.refund.succeeded.v1',
}

interface Envelope<T extends PaymentMessageType, D> {
    messageId: string;
    type: T;
    orderId: string;
    occurredAt: string;
    data: D;
}

export interface EnablePaymentData {
    reservationId: string;
    reservationExpiresAt: string;
    buyerId: string;
    amountCents: number;
    currency: 'MXN';
}
interface PaymentActionData {
    paymentId: string;
    reason: string;
}
export type EnablePayment = Envelope<PaymentMessageType.Enable, EnablePaymentData>;
export type CancelPayment = Envelope<PaymentMessageType.Cancel, PaymentActionData>;
export type RefundPayment = Envelope<PaymentMessageType.Refund, PaymentActionData>;
export type PaymentCommand = EnablePayment | CancelPayment | RefundPayment;
export type PaymentEvent =
    | Envelope<PaymentMessageType.Enabled, { paymentId: string; reservationId: string }>
    | Envelope<
          PaymentMessageType.Succeeded,
          { paymentId: string; reservationId: string; amountCents: number; currency: 'MXN' }
      >
    | Envelope<PaymentMessageType.NotCompleted, { paymentId: string; status: 'CANCELADO' | 'FALLIDO'; reason: string }>
    | Envelope<PaymentMessageType.RefundSucceeded, { paymentId: string; amountCents: number; currency: 'MXN' }>;
