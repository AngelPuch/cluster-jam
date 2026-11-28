import { Inject, Injectable } from '@nestjs/common';
import Stripe from 'stripe';
import type { PaymentAccessGateway } from '../../application/ports/payment-access.port';
import type { StripePaymentReference } from '../../application/ports/cancel-payment.port';
import { PaymentNotPayable } from '../../application/payments/payment-access.error';
import { PaymentProviderMismatch, PaymentProviderUnavailable } from '../../application/payments/payment.error';
import { STRIPE_CLIENT } from './stripe-intent.gateway';
import { parseStripePayment } from './stripe-payment.reader';
@Injectable()
export class StripePaymentAccessGateway implements PaymentAccessGateway {
    constructor(@Inject(STRIPE_CLIENT) private readonly stripe: Stripe | null) {}
    async clientSecret(expected: StripePaymentReference): Promise<string> {
        if (!this.stripe) throw new PaymentProviderUnavailable();
        let intent: Stripe.PaymentIntent;
        try {
            intent = await this.stripe.paymentIntents.retrieve(expected.id);
        } catch {
            throw new PaymentProviderUnavailable();
        }
        const current = parseStripePayment(intent, expected.id);
        if (
            !current ||
            current.paymentId !== expected.paymentId ||
            current.orderId !== expected.orderId ||
            current.buyerId !== expected.buyerId ||
            current.reservationId !== expected.reservationId ||
            current.amountCents !== expected.amountCents ||
            current.currency !== expected.currency
        )
            throw new PaymentProviderMismatch();
        if (!['requires_payment_method', 'requires_confirmation', 'requires_action'].includes(current.status))
            throw new PaymentNotPayable();
        if (typeof intent.client_secret !== 'string' || !intent.client_secret.startsWith(expected.id + '_secret_'))
            throw new PaymentProviderUnavailable();
        return intent.client_secret;
    }
}
