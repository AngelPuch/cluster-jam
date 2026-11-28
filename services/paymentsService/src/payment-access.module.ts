import { Module } from '@nestjs/common';
import { PaymentAccessService } from './application/payments/payment-access.service';
import {
    OWNED_PAYMENT_STORE,
    PAYMENT_ACCESS_GATEWAY,
    PAYMENT_TOKEN_VERIFIER,
} from './application/ports/payment-access.port';
import { DatabaseModule } from './infrastructure/database/database.module';
import { TypeormOwnedPaymentStore } from './infrastructure/database/typeorm-owned-payment.store';
import { SupabasePaymentJwtVerifier } from './infrastructure/security/supabase-payment-jwt.verifier';
import { StripePaymentAccessGateway } from './infrastructure/stripe/stripe-payment-access.gateway';
import { PaymentJwtGuard } from './interfaces/http/payments/payment-jwt.guard';
import { PaymentAccessController } from './interfaces/http/payments/payment-access.controller';
import { PaymentsModule } from './payments.module';
@Module({
    imports: [DatabaseModule, PaymentsModule],
    controllers: [PaymentAccessController],
    providers: [
        PaymentAccessService,
        PaymentJwtGuard,
        { provide: OWNED_PAYMENT_STORE, useClass: TypeormOwnedPaymentStore },
        { provide: PAYMENT_TOKEN_VERIFIER, useClass: SupabasePaymentJwtVerifier },
        { provide: PAYMENT_ACCESS_GATEWAY, useClass: StripePaymentAccessGateway },
    ],
})
export class PaymentAccessModule {}
