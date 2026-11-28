import { Inject, Injectable } from '@nestjs/common';
import Stripe from 'stripe';
import type {
    PaymentIntentGateway,
    PreparedPayment,
    ProviderIntent,
} from '../../application/ports/enable-payment.port';
import {
    PaymentProviderMismatch,
    PaymentProviderUnavailable,
    PaymentRecoveryRequired,
} from '../../application/payments/payment.error';

export const STRIPE_CLIENT = Symbol('STRIPE_CLIENT');
// Stay within Stripe's minimum 24-hour idempotency retention; an old unknown
// result requires recovery rather than a potentially new create request.
const CREATE_REPLAY_WINDOW_MS = 23 * 60 * 60 * 1000;

@Injectable()
export class StripeIntentGateway implements PaymentIntentGateway {
    constructor(@Inject(STRIPE_CLIENT) private readonly stripe: Stripe | null) {}

    async ensure(payment: PreparedPayment): Promise<ProviderIntent> {
        if (!this.stripe) throw new PaymentProviderUnavailable();
        if (!payment.stripePaymentIntentId && payment.creationAgeMs >= CREATE_REPLAY_WINDOW_MS) {
            throw new PaymentRecoveryRequired();
        }
        try {
            const intent = payment.stripePaymentIntentId
                ? await this.stripe.paymentIntents.retrieve(payment.stripePaymentIntentId)
                : await this.stripe.paymentIntents.create(
                      {
                          amount: payment.amountCents,
                          currency: 'mxn',
                          confirm: false,
                          allowed_payment_method_types: ['card'],
                          metadata: {
                              order_id: payment.orderId,
                              payment_id: payment.id,
                              reservation_id: payment.reservationId,
                              buyer_id: payment.buyerId,
                          },
                      },
                      { idempotencyKey: 'payment:create:' + payment.orderId },
                  );
            this.verify(intent, payment);
            return { id: intent.id, status: intent.status };
        } catch (error) {
            if (error instanceof PaymentProviderMismatch) throw error;
            throw new PaymentProviderUnavailable();
        }
    }

    private verify(intent: Stripe.PaymentIntent, payment: PreparedPayment): void {
        if (
            !intent.id?.startsWith('pi_') ||
            intent.livemode !== false ||
            intent.amount !== payment.amountCents ||
            intent.currency !== 'mxn' ||
            intent.metadata?.order_id !== payment.orderId ||
            intent.metadata?.payment_id !== payment.id ||
            intent.metadata?.reservation_id !== payment.reservationId ||
            intent.metadata?.buyer_id !== payment.buyerId
        ) {
            throw new PaymentProviderMismatch();
        }
    }
}
