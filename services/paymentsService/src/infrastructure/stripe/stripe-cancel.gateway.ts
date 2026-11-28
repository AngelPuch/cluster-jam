import { Inject, Injectable } from '@nestjs/common';
import Stripe from 'stripe';
import type { CancelPaymentGateway, StripePaymentReference } from '../../application/ports/cancel-payment.port';
import type { StripePaymentSnapshot } from '../../application/ports/payment-notice.port';
import { PaymentProviderMismatch, PaymentProviderUnavailable } from '../../application/payments/payment.error';
import { STRIPE_CLIENT } from './stripe-intent.gateway';
import { parseStripePayment } from './stripe-payment.reader';
@Injectable()
export class StripeCancelGateway implements CancelPaymentGateway {
    constructor(@Inject(STRIPE_CLIENT) private readonly stripe: Stripe | null) {}
    private verify(intent: Stripe.PaymentIntent, expected: StripePaymentReference): StripePaymentSnapshot {
        const actual = parseStripePayment(intent, expected.id);
        if (
            !actual ||
            actual.paymentId !== expected.paymentId ||
            actual.orderId !== expected.orderId ||
            actual.buyerId !== expected.buyerId ||
            actual.reservationId !== expected.reservationId ||
            actual.amountCents !== expected.amountCents ||
            actual.currency !== expected.currency
        )
            throw new PaymentProviderMismatch();
        return actual;
    }
    async cancel(payment: StripePaymentReference): Promise<StripePaymentSnapshot> {
        const stripe = this.stripe;
        if (!stripe) throw new PaymentProviderUnavailable();
        let current: StripePaymentSnapshot;
        try {
            current = this.verify(await stripe.paymentIntents.retrieve(payment.id), payment);
        } catch (error) {
            if (error instanceof PaymentProviderMismatch) throw error;
            throw new PaymentProviderUnavailable();
        }
        if (['succeeded', 'canceled'].includes(current.status)) return current;
        let result: Stripe.PaymentIntent;
        try {
            result = await stripe.paymentIntents.cancel(
                payment.id,
                {},
                { idempotencyKey: 'payment:cancel:' + payment.paymentId },
            );
        } catch {
            // Resolve a lost response or a simultaneous charge before retrying.
            try {
                result = await stripe.paymentIntents.retrieve(payment.id);
            } catch {
                throw new PaymentProviderUnavailable();
            }
        }
        const final = this.verify(result, payment);
        if (!['succeeded', 'canceled'].includes(final.status)) throw new PaymentProviderUnavailable();
        return final;
    }
}
