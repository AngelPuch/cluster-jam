import { Inject, Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import Stripe from 'stripe';
import type { PaymentNotice } from '../../application/ports/payment-notice.port';
import type { RefundNotice } from '../../application/ports/refund-payment.port';
import { PaymentProviderUnavailable } from '../../application/payments/payment.error';
import { STRIPE_CLIENT } from './stripe-intent.gateway';

export class InvalidStripeWebhook extends Error {
    constructor() {
        super('STRIPE_WEBHOOK_INVALID');
    }
}

@Injectable()
export class StripeWebhookVerifier {
    constructor(
        @Inject(STRIPE_CLIENT) private readonly stripe: Stripe | null,
        private readonly config: ConfigService,
    ) {}

    verify(body: Buffer | undefined, signature: unknown): PaymentNotice | RefundNotice | null {
        const secret = this.config.get<string>('STRIPE_WEBHOOK_SECRET');
        if (!this.stripe || !secret) throw new PaymentProviderUnavailable();
        if (!body || typeof signature !== 'string' || signature.length > 4096) throw new InvalidStripeWebhook();
        try {
            const event = this.stripe.webhooks.constructEvent(body, signature, secret, 300);
            if (
                event.object !== 'event' ||
                event.livemode !== false ||
                event.account ||
                !/^evt_[A-Za-z0-9]+$/.test(event.id) ||
                event.id.length > 255
            )
                throw new InvalidStripeWebhook();
            switch (event.type) {
                case 'payment_intent.succeeded':
                case 'payment_intent.canceled':
                case 'payment_intent.payment_failed':
                case 'payment_intent.processing': {
                    const intent = event.data.object;
                    if (
                        intent.object !== 'payment_intent' ||
                        !/^pi_[A-Za-z0-9]+$/.test(intent.id) ||
                        intent.id.length > 255
                    ) {
                        throw new InvalidStripeWebhook();
                    }
                    return { eventId: event.id, paymentIntentId: intent.id };
                }
                case 'refund.created':
                case 'refund.updated':
                case 'refund.failed': {
                    const refund = event.data.object;
                    if (refund.object !== 'refund' || !/^re_[A-Za-z0-9]+$/.test(refund.id) || refund.id.length > 255)
                        throw new InvalidStripeWebhook();
                    return { eventId: event.id, refundId: refund.id };
                }
                default:
                    return null;
            }
        } catch {
            throw new InvalidStripeWebhook();
        }
    }
}
