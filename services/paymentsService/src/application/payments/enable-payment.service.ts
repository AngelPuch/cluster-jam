import { Inject, Injectable } from '@nestjs/common';
import {
    ENABLE_PAYMENT_STORE,
    PAYMENT_INTENT_GATEWAY,
    type EnablePaymentStore,
    type PaymentIntentGateway,
} from '../ports/enable-payment.port';
import type { EnablePayment } from './payment-messages';

@Injectable()
export class EnablePaymentService {
    constructor(
        @Inject(ENABLE_PAYMENT_STORE) private readonly payments: EnablePaymentStore,
        @Inject(PAYMENT_INTENT_GATEWAY) private readonly provider: PaymentIntentGateway,
    ) {}

    async execute(command: EnablePayment): Promise<void> {
        const payment = await this.payments.prepare(command);
        if (!payment) return;
        // The provider call is outside the local business transaction.
        const intent = await this.provider.ensure(payment);
        await this.payments.complete(command, payment.id, intent);
    }
}
