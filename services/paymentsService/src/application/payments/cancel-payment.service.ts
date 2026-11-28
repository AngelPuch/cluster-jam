import { Inject, Injectable } from '@nestjs/common';
import {
    CANCEL_PAYMENT_STORE,
    CANCEL_PAYMENT_GATEWAY,
    type CancelPaymentStore,
    type CancelPaymentGateway,
} from '../ports/cancel-payment.port';
import type { CancelPayment } from './payment-messages';
@Injectable()
export class CancelPaymentService {
    constructor(
        @Inject(CANCEL_PAYMENT_STORE) private readonly store: CancelPaymentStore,
        @Inject(CANCEL_PAYMENT_GATEWAY) private readonly provider: CancelPaymentGateway,
    ) {}
    async execute(command: CancelPayment): Promise<void> {
        const payment = await this.store.prepare(command);
        if (payment) await this.store.complete(command, await this.provider.cancel(payment));
    }
}
