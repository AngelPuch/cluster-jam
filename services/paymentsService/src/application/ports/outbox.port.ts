export const OUTBOX_STORE = Symbol('OUTBOX_STORE');
export const PAYMENT_EVENT_PUBLISHER = Symbol('PAYMENT_EVENT_PUBLISHER');

export interface OutgoingPaymentEvent {
    id: string;
    exchange: string;
    routingKey: string;
    body: Record<string, unknown>;
}
export interface PaymentEventPublisher {
    publish(event: OutgoingPaymentEvent): Promise<void>;
}
export interface OutboxStore {
    publishNext(publish: (event: OutgoingPaymentEvent) => Promise<void>): Promise<boolean>;
}
