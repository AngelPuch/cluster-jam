import { Inject, Injectable } from '@nestjs/common';
import {
    REFUND_NOTICE_STORE,
    REFUND_GATEWAY,
    type RefundNoticeStore,
    type RefundGateway,
    type RefundNotice,
} from '../ports/refund-payment.port';
@Injectable()
export class ReceiveRefundNoticeService {
    constructor(
        @Inject(REFUND_NOTICE_STORE) private readonly store: RefundNoticeStore,
        @Inject(REFUND_GATEWAY) private readonly provider: RefundGateway,
    ) {}
    async execute(notice: RefundNotice): Promise<boolean> {
        if (await this.store.processed(notice.eventId)) return false;
        const refund = await this.provider.read(notice.refundId);
        if (!refund) return false;
        await this.store.apply(notice.eventId, refund);
        return ['failed', 'canceled'].includes(refund.status);
    }
}
