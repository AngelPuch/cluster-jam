import { Test } from '@nestjs/testing';
import type { INestApplication } from '@nestjs/common';
import { APP_FILTER } from '@nestjs/core';
import { ConfigService } from '@nestjs/config';
import { jest } from '@jest/globals';
import Stripe from 'stripe';
import request from 'supertest';
import { ReceivePaymentNoticeService } from '../src/application/payments/receive-payment-notice.service';
import { ReceiveRefundNoticeService } from '../src/application/payments/receive-refund-notice.service';
import type { PaymentNotice } from '../src/application/ports/payment-notice.port';
import { ObservabilityModule } from '../src/infrastructure/observability/observability.module';
import { STRIPE_CLIENT } from '../src/infrastructure/stripe/stripe-intent.gateway';
import { StripeWebhookVerifier } from '../src/infrastructure/stripe/stripe-webhook.verifier';
import { ProblemDetailsFilter } from '../src/interfaces/http/common/problem-details.filter';
import { configureHttpApplication } from '../src/interfaces/http/http.setup';
import { StripeWebhookController } from '../src/interfaces/http/stripe/stripe-webhook.controller';

describe('Stripe signed webhook HTTP', () => {
    let app: INestApplication;
    const stripe = new Stripe('sk_test_fixtureOnly');
    const secret = 'whsec_fixtureOnly';
    const config = new ConfigService({ STRIPE_WEBHOOK_SECRET: secret });
    const handler = { execute: jest.fn<(notice: PaymentNotice) => Promise<void>>().mockResolvedValue(undefined) };
    const event = {
        id: 'evt_fixture123',
        object: 'event',
        livemode: false,
        type: 'payment_intent.succeeded',
        data: { object: { id: 'pi_fixture123', object: 'payment_intent' } },
    };
    const sign = (payload: string, timestamp?: number) =>
        stripe.webhooks.generateTestHeaderString({ payload, secret, timestamp });

    beforeAll(async () => {
        const module = await Test.createTestingModule({
            imports: [ObservabilityModule],
            controllers: [StripeWebhookController],
            providers: [
                StripeWebhookVerifier,
                { provide: STRIPE_CLIENT, useValue: stripe },
                { provide: ConfigService, useValue: config },
                { provide: ReceivePaymentNoticeService, useValue: handler },
                { provide: ReceiveRefundNoticeService, useValue: { execute: () => Promise.resolve(false) } },
                { provide: APP_FILTER, useClass: ProblemDetailsFilter },
            ],
        }).compile();
        app = module.createNestApplication({ logger: false, rawBody: true });
        configureHttpApplication(app);
        await app.init();
    });
    afterAll(async () => {
        await app?.close();
    });
    beforeEach(() => {
        handler.execute.mockClear();
        config.set('STRIPE_WEBHOOK_SECRET', secret);
    });

    it('verifies the original bytes and rejects tampered, expired or live-mode notifications', async () => {
        const http = app.getHttpServer() as Parameters<typeof request>[0];
        const payload = JSON.stringify(event, null, 2);
        await request(http)
            .post('/api/v1/webhooks/stripe')
            .set('Content-Type', 'application/json')
            .set('Stripe-Signature', sign(payload))
            .send(payload)
            .expect(200, { received: true });
        expect(handler.execute).toHaveBeenCalledWith({ eventId: event.id, paymentIntentId: 'pi_fixture123' });
        handler.execute.mockClear();
        await request(http)
            .post('/api/v1/webhooks/stripe')
            .set('Content-Type', 'application/json')
            .set('Stripe-Signature', sign(payload))
            .send(JSON.stringify(event))
            .expect(400);
        await request(http)
            .post('/api/v1/webhooks/stripe')
            .set('Content-Type', 'application/json')
            .set('Stripe-Signature', sign(payload, Math.floor(Date.now() / 1000) - 1000))
            .send(payload)
            .expect(400);
        const live = JSON.stringify({ ...event, livemode: true });
        await request(http)
            .post('/api/v1/webhooks/stripe')
            .set('Content-Type', 'application/json')
            .set('Stripe-Signature', sign(live))
            .send(live)
            .expect(400);
        expect(handler.execute).not.toHaveBeenCalled();
    });

    it('ignores unrelated event types and returns retryable unavailability when unconfigured', async () => {
        const http = app.getHttpServer() as Parameters<typeof request>[0];
        const payload = JSON.stringify({ ...event, type: 'customer.created' });
        await request(http)
            .post('/api/v1/webhooks/stripe')
            .set('Content-Type', 'application/json')
            .set('Stripe-Signature', sign(payload))
            .send(payload)
            .expect(200);
        config.set('STRIPE_WEBHOOK_SECRET', '');
        const response = await request(http)
            .post('/api/v1/webhooks/stripe')
            .set('Content-Type', 'application/json')
            .set('Stripe-Signature', sign(payload))
            .send(payload)
            .expect(503);
        expect(response.body).toMatchObject({ code: 'SERVICE_UNAVAILABLE' });
        expect(JSON.stringify(response.body)).not.toContain(secret);
        expect(handler.execute).not.toHaveBeenCalled();
        const contract = await request(http).get('/openapi.json').expect(200);
        expect(Object.keys((contract.body as { paths: object }).paths)).toContain('/api/v1/webhooks/stripe');
    });
});
