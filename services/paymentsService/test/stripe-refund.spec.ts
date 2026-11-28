import 'reflect-metadata';
import { randomUUID } from 'node:crypto';
import type Stripe from 'stripe';
import type { PreparedRefund } from '../src/application/ports/refund-payment.port';
import {
    PaymentProviderMismatch,
    PaymentProviderUnavailable,
    PaymentRecoveryRequired,
} from '../src/application/payments/payment.error';
import { StripeIntentGateway } from '../src/infrastructure/stripe/stripe-intent.gateway';
import { StripeRefundGateway } from '../src/infrastructure/stripe/stripe-refund.gateway';
import { StripeFixture } from './stripe-fixture';
async function paid(stripe: Stripe, fixture: StripeFixture): Promise<PreparedRefund> {
    const prepared = {
        id: randomUUID(),
        orderId: randomUUID(),
        buyerId: randomUUID(),
        reservationId: randomUUID(),
        amountCents: 19900,
        currency: 'MXN' as const,
        stripePaymentIntentId: null,
        creationAgeMs: 0,
    };
    const intent = await new StripeIntentGateway(stripe).ensure(prepared);
    const remote = fixture.intents.get('payment:create:' + prepared.orderId);
    if (!remote) throw new Error('Missing fixture intent.');
    remote.status = 'succeeded';
    remote.amount_received = 19900;
    return {
        id: randomUUID(),
        stripeRefundId: null,
        creationAgeMs: 0,
        payment: {
            id: intent.id,
            paymentId: prepared.id,
            orderId: prepared.orderId,
            buyerId: prepared.buyerId,
            reservationId: prepared.reservationId,
            amountCents: 19900,
            currency: 'MXN',
        },
    };
}
describe('Full refunds using the real Stripe SDK', () => {
    it('recovers a lost response with one full refund and the stable payment key', async () => {
        const fixture = new StripeFixture();
        try {
            const stripe = await fixture.open();
            const prepared = await paid(stripe, fixture);
            const gateway = new StripeRefundGateway(stripe);
            fixture.dropRefundResponses = 2;
            await expect(gateway.ensure(prepared)).rejects.toBeInstanceOf(PaymentProviderUnavailable);
            const result = await gateway.ensure(prepared);
            expect(result.status).toBe('succeeded');
            expect(fixture.refunds.size).toBe(1);
            expect(
                fixture.refundRequests.every(
                    (call) =>
                        call.key === 'payment:refund:' + prepared.payment.paymentId &&
                        call.form.get('amount') === '19900',
                ),
            ).toBe(true);
            expect((await gateway.ensure({ ...prepared, stripeRefundId: result.id })).id).toBe(result.id);
            expect(fixture.refunds.size).toBe(1);
        } finally {
            await fixture.close();
        }
    });
    it('blocks another owner and an old unknown refund before creating another operation', async () => {
        const fixture = new StripeFixture();
        try {
            const stripe = await fixture.open();
            const prepared = await paid(stripe, fixture);
            const gateway = new StripeRefundGateway(stripe);
            await expect(
                gateway.ensure({ ...prepared, payment: { ...prepared.payment, buyerId: randomUUID() } }),
            ).rejects.toBeInstanceOf(PaymentProviderMismatch);
            await expect(gateway.ensure({ ...prepared, creationAgeMs: 23 * 60 * 60 * 1000 })).rejects.toBeInstanceOf(
                PaymentRecoveryRequired,
            );
            expect(fixture.refundRequests).toHaveLength(0);
        } finally {
            await fixture.close();
        }
    });
});
