import { Inject, Injectable } from '@nestjs/common';
import { isUUID } from 'class-validator';
import Stripe from 'stripe';
import type { StripePaymentReader, StripePaymentSnapshot } from '../../application/ports/payment-notice.port';
import { PaymentProviderMismatch, PaymentProviderUnavailable } from '../../application/payments/payment.error';
import { STRIPE_CLIENT } from './stripe-intent.gateway';

const STATUSES: ReadonlySet<string> = new Set([
    'requires_payment_method',
    'requires_confirmation',
    'requires_action',
    'processing',
    'requires_capture',
    'canceled',
    'succeeded',
]);
function identifier(value: unknown): string {
    if (typeof value !== 'string' || !isUUID(value)) throw new PaymentProviderMismatch();
    return value.toLowerCase();
}

@Injectable()
export class StripeCurrentPaymentReader implements StripePaymentReader {
    constructor(@Inject(STRIPE_CLIENT) private readonly stripe: Stripe | null) {}

    async read(id: string): Promise<StripePaymentSnapshot | null> {
        if (!this.stripe) throw new PaymentProviderUnavailable();
        let intent: Stripe.PaymentIntent;
        try {
            intent = await this.stripe.paymentIntents.retrieve(id);
        } catch {
            throw new PaymentProviderUnavailable();
        }
        return parseStripePayment(intent, id);
    }
}
export function parseStripePayment(intent: Stripe.PaymentIntent, id: string): StripePaymentSnapshot | null {
    if (intent.id !== id || intent.object !== 'payment_intent' || intent.livemode !== false)
        throw new PaymentProviderMismatch();
    // An account can contain payments unrelated to Cluster JAM.
    if (!intent.metadata?.payment_id) return null;
    if (
        !Number.isSafeInteger(intent.amount) ||
        intent.amount < 1 ||
        intent.currency !== 'mxn' ||
        !STATUSES.has(intent.status) ||
        !Number.isSafeInteger(intent.amount_received) ||
        intent.amount_received < 0 ||
        (intent.status === 'succeeded' && intent.amount_received !== intent.amount) ||
        (intent.status === 'canceled' && intent.amount_received !== 0)
    )
        throw new PaymentProviderMismatch();
    return {
        id: intent.id,
        paymentId: identifier(intent.metadata.payment_id),
        orderId: identifier(intent.metadata.order_id),
        buyerId: identifier(intent.metadata.buyer_id),
        reservationId: identifier(intent.metadata.reservation_id),
        amountCents: intent.amount,
        currency: 'MXN',
        status: intent.status,
    };
}
