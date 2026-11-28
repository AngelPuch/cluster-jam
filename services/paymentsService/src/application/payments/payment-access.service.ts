import { Inject, Injectable } from '@nestjs/common';
import {
    OWNED_PAYMENT_STORE,
    PAYMENT_ACCESS_GATEWAY,
    type OwnedPaymentStore,
    type PaymentAccessGateway,
    type OwnedPayment,
} from '../ports/payment-access.port';
import { PaymentStatus } from './payment';
import { PaymentNotFound, PaymentNotPayable } from './payment-access.error';
@Injectable()
export class PaymentAccessService {
    constructor(
        @Inject(OWNED_PAYMENT_STORE) private readonly store: OwnedPaymentStore,
        @Inject(PAYMENT_ACCESS_GATEWAY) private readonly provider: PaymentAccessGateway,
    ) {}
    private async owned(id: string, buyerId: string): Promise<OwnedPayment> {
        const payment = await this.store.findOwned(id, buyerId);
        if (!payment) throw new PaymentNotFound();
        return payment;
    }
    async summary(id: string, buyerId: string) {
        const payment = await this.owned(id, buyerId);
        return {
            paymentId: payment.paymentId,
            orderId: payment.orderId,
            status: payment.status,
            amountCents: payment.amountCents,
            currency: payment.currency,
            refundStatus: payment.refundStatus,
        };
    }
    async access(id: string, buyerId: string): Promise<{ paymentId: string; clientSecret: string }> {
        const payment = await this.owned(id, buyerId);
        if (payment.status !== PaymentStatus.Pending || !payment.reservationActive || !payment.reference)
            throw new PaymentNotPayable();
        const clientSecret = await this.provider.clientSecret(payment.reference);
        // Recheck eligibility after the external read; never hold a SQL lock through it.
        const latest = await this.owned(id, buyerId);
        if (
            latest.status !== PaymentStatus.Pending ||
            !latest.reservationActive ||
            latest.reference?.id !== payment.reference.id
        )
            throw new PaymentNotPayable();
        return { paymentId: payment.paymentId, clientSecret };
    }
}
