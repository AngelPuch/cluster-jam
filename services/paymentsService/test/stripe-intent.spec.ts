import 'reflect-metadata';
import { randomUUID } from 'node:crypto';
import type { PreparedPayment } from '../src/application/ports/enable-payment.port';
import {
    PaymentProviderMismatch,
    PaymentProviderUnavailable,
    PaymentRecoveryRequired,
} from '../src/application/payments/payment.error';
import { StripeIntentGateway } from '../src/infrastructure/stripe/stripe-intent.gateway';
import { StripeFixture } from './stripe-fixture';

function payment(): PreparedPayment {
    return {
        id: randomUUID(),
        orderId: randomUUID(),
        buyerId: randomUUID(),
        reservationId: randomUUID(),
        amountCents: 19900,
        currency: 'MXN',
        stripePaymentIntentId: null,
        creationAgeMs: 0,
    };
}

describe('Stripe test-mode adapter using the real SDK', () => {
    it('reuses one unconfirmed intent, the stable order key and trusted amount without exposing its secret', async () => {
        const fixture = new StripeFixture();
        try {
            const gateway = new StripeIntentGateway(await fixture.open());
            const prepared = payment();
            fixture.dropCreateResponses = 1;
            const first = await gateway.ensure(prepared);
            expect(await gateway.ensure(prepared)).toEqual(first);
            expect(await gateway.ensure({ ...prepared, stripePaymentIntentId: first.id })).toEqual(first);
            expect(fixture.intents.size).toBe(1);
            expect(fixture.requests).toHaveLength(3);
            expect(fixture.requests[0].key).toBe('payment:create:' + prepared.orderId);
            expect(Object.fromEntries(fixture.requests[0].form)).toMatchObject({
                amount: '19900',
                currency: 'mxn',
                confirm: 'false',
                'allowed_payment_method_types[0]': 'card',
                'metadata[payment_id]': prepared.id,
            });
            expect(first).toEqual({ id: 'pi_fixture1', status: 'requires_payment_method' });
        } finally {
            await fixture.close();
        }
    });

    it('rejects mismatched financial evidence and refuses an old unknown create result', async () => {
        const fixture = new StripeFixture();
        try {
            const gateway = new StripeIntentGateway(await fixture.open());
            const prepared = payment();
            fixture.dropCreateResponses = 2;
            await expect(gateway.ensure(prepared)).rejects.toBeInstanceOf(PaymentProviderUnavailable);
            for (const response of [{ amount: 1 }, { livemode: true }, { metadata: {} }]) {
                fixture.responseOverride = response;
                await expect(gateway.ensure(prepared)).rejects.toBeInstanceOf(PaymentProviderMismatch);
            }
            const before = fixture.requests.length;
            await expect(gateway.ensure({ ...prepared, creationAgeMs: 23 * 60 * 60 * 1000 })).rejects.toBeInstanceOf(
                PaymentRecoveryRequired,
            );
            expect(fixture.requests).toHaveLength(before);
        } finally {
            await fixture.close();
        }
    });
});
