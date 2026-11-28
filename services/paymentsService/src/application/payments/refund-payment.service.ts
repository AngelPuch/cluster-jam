import { Inject, Injectable } from '@nestjs/common';
import {
    REFUND_PAYMENT_STORE,
    REFUND_GATEWAY,
    type RefundPaymentStore,
    type RefundGateway,
} from '../ports/refund-payment.port';
import { PaymentRecoveryRequired } from './payment.error';
import type { RefundPayment } from './payment-messages';
@Injectable()
export class RefundPaymentService {
    constructor(
        @Inject(REFUND_PAYMENT_STORE) private readonly store: RefundPaymentStore,
        @Inject(REFUND_GATEWAY) private readonly provider: RefundGateway,
    ) {}
    async execute(command: RefundPayment): Promise<void> {
        const prepared = await this.store.prepare(command);
        if (!prepared) return;
        const refund = await this.provider.ensure(prepared);
        await this.store.complete(command, refund);
        if (['failed', 'canceled'].includes(refund.status)) throw new PaymentRecoveryRequired();
    }
}
