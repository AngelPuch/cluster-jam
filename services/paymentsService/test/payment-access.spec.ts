import { Test } from '@nestjs/testing';
import type { INestApplication } from '@nestjs/common';
import { APP_FILTER } from '@nestjs/core';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { DataSource } from 'typeorm';
import { createServer } from 'node:http';
import { randomUUID } from 'node:crypto';
import { generateKeyPair, exportJWK, SignJWT, type JWTPayload } from 'jose';
import request from 'supertest';
import { OWNED_PAYMENT_STORE, type OwnedPayment } from '../src/application/ports/payment-access.port';
import { PaymentStatus } from '../src/application/payments/payment';
import { ObservabilityModule } from '../src/infrastructure/observability/observability.module';
import { STRIPE_CLIENT, StripeIntentGateway } from '../src/infrastructure/stripe/stripe-intent.gateway';
import { configureHttpApplication } from '../src/interfaces/http/http.setup';
import { ProblemDetailsFilter } from '../src/interfaces/http/common/problem-details.filter';
import { PaymentAccessModule } from '../src/payment-access.module';
import { StripeFixture } from './stripe-fixture';

describe('Owner-only payment access with signed JWT and real SDK', () => {
    let app: INestApplication;
    let pair: Awaited<ReturnType<typeof generateKeyPair>>;
    let origin: string;
    let record: OwnedPayment;
    let clientSecret: string;
    const owner = randomUUID();
    const fixture = new StripeFixture();
    const jwksServer = createServer();
    async function token(sub = owner, claims: JWTPayload = {}) {
        return new SignJWT({ role: 'authenticated', is_anonymous: false, ...claims })
            .setProtectedHeader({ alg: 'ES256', kid: 'payments-test' })
            .setSubject(sub)
            .setIssuer(origin + '/auth/v1')
            .setAudience('authenticated')
            .setIssuedAt()
            .setExpirationTime(claims.exp ?? '5m')
            .sign(pair.privateKey);
    }
    beforeAll(async () => {
        pair = await generateKeyPair('ES256');
        const publicKey = { ...(await exportJWK(pair.publicKey)), kid: 'payments-test', alg: 'ES256', use: 'sig' };
        jwksServer.on('request', (req, res) => {
            if (req.url !== '/auth/v1/.well-known/jwks.json') {
                res.writeHead(404).end();
                return;
            }
            res.writeHead(200, { 'Content-Type': 'application/json' }).end(JSON.stringify({ keys: [publicKey] }));
        });
        await new Promise<void>((resolve) => jwksServer.listen(0, '127.0.0.1', resolve));
        const address = jwksServer.address();
        if (!address || typeof address === 'string') throw new Error('JWKS fixture did not bind.');
        origin = 'http://127.0.0.1:' + address.port;
        const stripe = await fixture.open();
        const prepared = {
            id: randomUUID(),
            orderId: randomUUID(),
            buyerId: owner,
            reservationId: randomUUID(),
            amountCents: 19900,
            currency: 'MXN' as const,
            stripePaymentIntentId: null,
            creationAgeMs: 0,
        };
        const intent = await new StripeIntentGateway(stripe).ensure(prepared);
        const remote = fixture.intents.get('payment:create:' + prepared.orderId);
        if (typeof remote?.client_secret !== 'string') throw new Error('Missing fixture secret.');
        clientSecret = remote.client_secret;
        record = {
            paymentId: prepared.id,
            orderId: prepared.orderId,
            amountCents: 19900,
            currency: 'MXN',
            status: PaymentStatus.Pending,
            reservationActive: true,
            refundStatus: null,
            reference: {
                id: intent.id,
                paymentId: prepared.id,
                orderId: prepared.orderId,
                buyerId: owner,
                reservationId: prepared.reservationId,
                amountCents: 19900,
                currency: 'MXN',
            },
        };
        const module = await Test.createTestingModule({
            imports: [
                ConfigModule.forRoot({ isGlobal: true, ignoreEnvFile: true }),
                ObservabilityModule,
                PaymentAccessModule,
            ],
            providers: [{ provide: APP_FILTER, useClass: ProblemDetailsFilter }],
        })
            .overrideProvider(ConfigService)
            .useValue(new ConfigService({ SUPABASE_URL: origin }))
            .overrideProvider(DataSource)
            .useValue({ isInitialized: false })
            .overrideProvider(OWNED_PAYMENT_STORE)
            .useValue({
                findOwned: (id: string, buyer: string) =>
                    Promise.resolve(id === record.paymentId && buyer === owner ? record : null),
            })
            .overrideProvider(STRIPE_CLIENT)
            .useValue(stripe)
            .compile();
        app = module.createNestApplication({ logger: false });
        configureHttpApplication(app);
        await app.init();
    });
    afterAll(async () => {
        await app?.close();
        await fixture.close();
        await new Promise<void>((resolve) => {
            jwksServer.close(() => resolve());
            jwksServer.closeAllConnections();
        });
    });
    it('rejects missing, invalid, expired and service-role credentials before reading payment secrets', async () => {
        const http = app.getHttpServer() as Parameters<typeof request>[0];
        const path = '/api/v1/payments/' + record.paymentId + '/client-secret';
        await request(http).get(path).expect(401);
        await request(http).get(path).set('Authorization', 'Bearer invalid').expect(401);
        const wrongKey = await generateKeyPair('ES256');
        const forged = await new SignJWT({ role: 'authenticated' })
            .setProtectedHeader({ alg: 'ES256', kid: 'payments-test' })
            .setSubject(owner)
            .setIssuer(origin + '/auth/v1')
            .setAudience('authenticated')
            .setExpirationTime('5m')
            .sign(wrongKey.privateKey);
        await request(http)
            .get(path)
            .set('Authorization', 'Bearer ' + forged)
            .expect(401);
        await request(http)
            .get(path)
            .set('Authorization', 'Bearer ' + (await token(owner, { exp: Math.floor(Date.now() / 1000) - 60 })))
            .expect(401);
        await request(http)
            .get(path)
            .set('Authorization', 'Bearer ' + (await token(owner, { role: 'service_role' })))
            .expect(401);
        expect(fixture.retrievals).toHaveLength(0);
    });
    it('hides other buyers, reveals only the owned payable intent and blocks expired or paid access', async () => {
        const http = app.getHttpServer() as Parameters<typeof request>[0];
        const path = '/api/v1/payments/' + record.paymentId;
        const other = await token(randomUUID());
        await request(http)
            .get(path)
            .set('Authorization', 'Bearer ' + other)
            .set('X-User-Id', owner)
            .expect(404);
        await request(http)
            .get(path + '/client-secret')
            .set('Authorization', 'Bearer ' + other)
            .expect(404);
        expect(fixture.retrievals).toHaveLength(0);
        const authorization = 'Bearer ' + (await token());
        const summary = await request(http).get(path).set('Authorization', authorization).expect(200);
        expect(summary.body).toMatchObject({ paymentId: record.paymentId, amountCents: 19900, currency: 'MXN' });
        expect(JSON.stringify(summary.body)).not.toContain('secret');
        const access = await request(http)
            .get(path + '/client-secret')
            .set('Authorization', authorization)
            .expect(200);
        expect(access.body).toEqual({ paymentId: record.paymentId, clientSecret });
        expect(access.headers['cache-control']).toBe('no-store');
        record.reservationActive = false;
        await request(http)
            .get(path + '/client-secret')
            .set('Authorization', authorization)
            .expect(409);
        record.reservationActive = true;
        record.status = PaymentStatus.Paid;
        await request(http)
            .get(path + '/client-secret')
            .set('Authorization', authorization)
            .expect(409);
        expect(fixture.retrievals).toHaveLength(1);
    });
});
