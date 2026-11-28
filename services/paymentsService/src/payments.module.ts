import { Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import Stripe from 'stripe';
import { EnablePaymentService } from './application/payments/enable-payment.service';
import { ENABLE_PAYMENT_STORE, PAYMENT_INTENT_GATEWAY } from './application/ports/enable-payment.port';
import { DatabaseModule } from './infrastructure/database/database.module';
import { TypeormEnablePaymentStore } from './infrastructure/database/typeorm-enable-payment.store';
import { STRIPE_CLIENT, StripeIntentGateway } from './infrastructure/stripe/stripe-intent.gateway';

@Module({
    imports: [DatabaseModule],
    providers: [
        EnablePaymentService,
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
