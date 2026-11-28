import { Inject, Injectable } from '@nestjs/common';
import {
    PAYMENT_NOTICE_STORE,
    STRIPE_PAYMENT_READER,
    type PaymentNoticeStore,
    type StripePaymentReader,
    type PaymentNotice,
} from '../ports/payment-notice.port';

@Injectable()
export class ReceivePaymentNoticeService {
    constructor(
        @Inject(PAYMENT_NOTICE_STORE) private readonly store: PaymentNoticeStore,
        @Inject(STRIPE_PAYMENT_READER) private readonly provider: StripePaymentReader,
    ) {}

    async execute(notice: PaymentNotice): Promise<void> {
        if (await this.store.processed(notice.eventId)) return;
        // Read current provider state outside the business SQL transaction.
        const snapshot = await this.provider.read(notice.paymentIntentId);
        if (snapshot) await this.store.apply(notice.eventId, snapshot);
    }
}
