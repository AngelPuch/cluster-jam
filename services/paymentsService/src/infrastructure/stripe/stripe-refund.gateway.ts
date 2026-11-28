import { Inject, Injectable } from '@nestjs/common';
import { isUUID } from 'class-validator';
import Stripe from 'stripe';
import type { RefundGateway, PreparedRefund, RefundSnapshot } from '../../application/ports/refund-payment.port';
import {
    PaymentProviderMismatch,
    PaymentProviderUnavailable,
    PaymentRecoveryRequired,
} from '../../application/payments/payment.error';
import { STRIPE_CLIENT } from './stripe-intent.gateway';
import { parseStripePayment } from './stripe-payment.reader';
@Injectable()
export class StripeRefundGateway implements RefundGateway {
    constructor(@Inject(STRIPE_CLIENT) private readonly stripe: Stripe | null) {}
    private async snapshot(refund: Stripe.Refund): Promise<RefundSnapshot | null> {
        if (!refund.metadata?.refund_id) return null;
        const paymentIntentId =
            typeof refund.payment_intent === 'string' ? refund.payment_intent : refund.payment_intent?.id;
        if (!paymentIntentId || !this.stripe) throw new PaymentProviderMismatch();
        let intent: Stripe.PaymentIntent;
        try {
            intent = await this.stripe.paymentIntents.retrieve(paymentIntentId);
        } catch {
            throw new PaymentProviderUnavailable();
        }
        const payment = parseStripePayment(intent, paymentIntentId);
        if (
            !payment ||
            payment.status !== 'succeeded' ||
            refund.object !== 'refund' ||
            !/^re_[A-Za-z0-9]+$/.test(refund.id) ||
            !isUUID(refund.metadata.refund_id) ||
            refund.metadata.payment_id?.toLowerCase() !== payment.paymentId ||
            refund.metadata.order_id?.toLowerCase() !== payment.orderId ||
            refund.amount !== payment.amountCents ||
            refund.currency !== 'mxn' ||
            !refund.status ||
            !['pending', 'requires_action', 'succeeded', 'failed', 'canceled'].includes(refund.status)
        )
            throw new PaymentProviderMismatch();
        return { id: refund.id, refundId: refund.metadata.refund_id.toLowerCase(), payment, status: refund.status };
    }
    async read(id: string): Promise<RefundSnapshot | null> {
        if (!this.stripe) throw new PaymentProviderUnavailable();
        let refund: Stripe.Refund;
        try {
            refund = await this.stripe.refunds.retrieve(id);
        } catch {
            throw new PaymentProviderUnavailable();
        }
        if (refund.id !== id) throw new PaymentProviderMismatch();
        return this.snapshot(refund);
    }
    async ensure(prepared: PreparedRefund): Promise<RefundSnapshot> {
        if (!this.stripe) throw new PaymentProviderUnavailable();
        if (!prepared.stripeRefundId && prepared.creationAgeMs >= 23 * 60 * 60 * 1000)
            throw new PaymentRecoveryRequired();
        let intent: Stripe.PaymentIntent;
        try {
            intent = await this.stripe.paymentIntents.retrieve(prepared.payment.id);
        } catch {
            throw new PaymentProviderUnavailable();
        }
        const payment = parseStripePayment(intent, prepared.payment.id);
        if (
            !payment ||
            payment.status !== 'succeeded' ||
            payment.paymentId !== prepared.payment.paymentId ||
            payment.orderId !== prepared.payment.orderId ||
            payment.buyerId !== prepared.payment.buyerId ||
            payment.reservationId !== prepared.payment.reservationId ||
            payment.amountCents !== prepared.payment.amountCents ||
            payment.currency !== prepared.payment.currency
        )
            throw new PaymentProviderMismatch();
        let refund: Stripe.Refund;
        try {
            refund = prepared.stripeRefundId
                ? await this.stripe.refunds.retrieve(prepared.stripeRefundId)
                : await this.stripe.refunds.create(
                      {
                          payment_intent: payment.id,
                          amount: payment.amountCents,
                          metadata: {
                              refund_id: prepared.id,
                              payment_id: payment.paymentId,
                              order_id: payment.orderId,
                          },
                      },
                      { idempotencyKey: 'payment:refund:' + payment.paymentId },
                  );
        } catch {
            throw new PaymentProviderUnavailable();
        }
        const result = await this.snapshot(refund);
        if (
            !result ||
            result.refundId !== prepared.id ||
            result.payment.id !== prepared.payment.id ||
            (prepared.stripeRefundId && result.id !== prepared.stripeRefundId)
        )
            throw new PaymentProviderMismatch();
        return result;
    }
}
