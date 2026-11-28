import { Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import Stripe from 'stripe';
import { EnablePaymentService } from './application/payments/enable-payment.service';
import { ENABLE_PAYMENT_STORE, PAYMENT_INTENT_GATEWAY } from './application/ports/enable-payment.port';
import { DatabaseModule } from './infrastructure/database/database.module';
import { TypeormEnablePaymentStore } from './infrastructure/database/typeorm-enable-payment.store';
import { STRIPE_CLIENT, StripeIntentGateway } from './infrastructure/stripe/stripe-intent.gateway';
import { ReceivePaymentNoticeService } from './application/payments/receive-payment-notice.service';
import { PAYMENT_NOTICE_STORE, STRIPE_PAYMENT_READER } from './application/ports/payment-notice.port';
import { TypeormPaymentNoticeStore } from './infrastructure/database/typeorm-payment-notice.store';
import { StripeCurrentPaymentReader } from './infrastructure/stripe/stripe-payment.reader';
import { StripeWebhookVerifier } from './infrastructure/stripe/stripe-webhook.verifier';
import { StripeWebhookController } from './interfaces/http/stripe/stripe-webhook.controller';

@Module({
    imports: [DatabaseModule],
    controllers: [StripeWebhookController],
    providers: [
        EnablePaymentService,
        ReceivePaymentNoticeService,
        StripeWebhookVerifier,
        { provide: PAYMENT_NOTICE_STORE, useClass: TypeormPaymentNoticeStore },
        { provide: STRIPE_PAYMENT_READER, useClass: StripeCurrentPaymentReader },
        { provide: ENABLE_PAYMENT_STORE, useClass: TypeormEnablePaymentStore },
        { provide: PAYMENT_INTENT_GATEWAY, useClass: StripeIntentGateway },
        {
            provide: STRIPE_CLIENT,
            inject: [ConfigService],
            useFactory: (config: ConfigService) => {
                const key = config.get<string>('STRIPE_SECRET_KEY');
                return key
                    ? new Stripe(key, {
                          apiVersion: '2026-11-18.endive',
                          timeout: 5000,
                          maxNetworkRetries: 0,
                          telemetry: false,
                      })
                    : null;
            },
        },
    ],
    exports: [EnablePaymentService],
})
export class PaymentsModule {}
