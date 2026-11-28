import 'reflect-metadata';
import { randomUUID } from 'node:crypto';
import type Stripe from 'stripe';
import type { StripePaymentReference } from '../src/application/ports/cancel-payment.port';
import { PaymentProviderMismatch, PaymentProviderUnavailable } from '../src/application/payments/payment.error';
import { StripeIntentGateway } from '../src/infrastructure/stripe/stripe-intent.gateway';
import { StripeCancelGateway } from '../src/infrastructure/stripe/stripe-cancel.gateway';
import { StripeFixture } from './stripe-fixture';

async function payment(stripe: Stripe): Promise<StripePaymentReference> {
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
    return {
        id: intent.id,
        paymentId: prepared.id,
        orderId: prepared.orderId,
        buyerId: prepared.buyerId,
        reservationId: prepared.reservationId,
        amountCents: prepared.amountCents,
        currency: prepared.currency,
    };
}
describe('Stripe cancellation using the real SDK', () => {
    it('recovers a lost cancel response and reuses the original payment operation', async () => {
        const fixture = new StripeFixture();
        try {
            const stripe = await fixture.open();
            const expected = await payment(stripe);
            const gateway = new StripeCancelGateway(stripe);
            fixture.dropCancelResponses = 2;
            expect((await gateway.cancel(expected)).status).toBe('canceled');
            expect((await gateway.cancel(expected)).status).toBe('canceled');
            expect(fixture.cancelEffects).toBe(1);
            expect(fixture.cancellations).toHaveLength(2);
            expect(fixture.cancellations.every((call) => call.key === 'payment:cancel:' + expected.paymentId)).toBe(
                true,
            );
        } finally {
            await fixture.close();
        }
    });
    it('rejects another owner, credits a charge that wins the race and keeps uncertain processing unresolved', async () => {
        const fixture = new StripeFixture();
        try {
            const stripe = await fixture.open();
            const expected = await payment(stripe);
            const gateway = new StripeCancelGateway(stripe);
            await expect(gateway.cancel({ ...expected, buyerId: randomUUID() })).rejects.toBeInstanceOf(
                PaymentProviderMismatch,
            );
            expect(fixture.cancellations).toHaveLength(0);
            fixture.succeedOnNextCancel = true;
            expect((await gateway.cancel(expected)).status).toBe('succeeded');
            fixture.blockCancellation = true;
            await expect(gateway.cancel(await payment(stripe))).rejects.toBeInstanceOf(PaymentProviderUnavailable);
            expect(fixture.cancelEffects).toBe(0);
        } finally {
            await fixture.close();
        }
    });
});
