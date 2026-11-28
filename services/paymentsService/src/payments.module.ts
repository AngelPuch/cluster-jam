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
import { CancelPaymentService } from './application/payments/cancel-payment.service';
import { CANCEL_PAYMENT_STORE, CANCEL_PAYMENT_GATEWAY } from './application/ports/cancel-payment.port';
import { TypeormCancelPaymentStore } from './infrastructure/database/typeorm-cancel-payment.store';
import { StripeCancelGateway } from './infrastructure/stripe/stripe-cancel.gateway';
import { RefundPaymentService } from './application/payments/refund-payment.service';
import { ReceiveRefundNoticeService } from './application/payments/receive-refund-notice.service';
import { REFUND_PAYMENT_STORE, REFUND_GATEWAY, REFUND_NOTICE_STORE } from './application/ports/refund-payment.port';
import { TypeormRefundStore } from './infrastructure/database/typeorm-refund.store';
import { TypeormRefundNoticeStore } from './infrastructure/database/typeorm-refund-notice.store';
import { StripeRefundGateway } from './infrastructure/stripe/stripe-refund.gateway';

@Module({
    imports: [DatabaseModule],
    controllers: [StripeWebhookController],
    providers: [
        EnablePaymentService,
        CancelPaymentService,
        RefundPaymentService,
        ReceiveRefundNoticeService,
        { provide: REFUND_PAYMENT_STORE, useClass: TypeormRefundStore },
        { provide: REFUND_GATEWAY, useClass: StripeRefundGateway },
        { provide: REFUND_NOTICE_STORE, useClass: TypeormRefundNoticeStore },
        { provide: CANCEL_PAYMENT_STORE, useClass: TypeormCancelPaymentStore },
        { provide: CANCEL_PAYMENT_GATEWAY, useClass: StripeCancelGateway },
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
    exports: [EnablePaymentService, CancelPaymentService, RefundPaymentService],
})
export class PaymentsModule {}
