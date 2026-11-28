import { Injectable } from '@nestjs/common';
import { DataSource } from 'typeorm';
import type { OwnedPaymentStore, OwnedPayment } from '../../application/ports/payment-access.port';
import { PaymentPersistenceUnavailable } from '../../application/payments/payment.error';
import { DatabaseReadiness } from './database-readiness.service';
import { PaymentEntity } from './entities/payment.entity';
import { RefundEntity } from './entities/refund.entity';
@Injectable()
export class TypeormOwnedPaymentStore implements OwnedPaymentStore {
    constructor(
        private readonly database: DataSource,
        private readonly readiness: DatabaseReadiness,
    ) {}
    async findOwned(paymentId: string, buyerId: string): Promise<OwnedPayment | null> {
        if (!(await this.readiness.check())) throw new PaymentPersistenceUnavailable();
        const payment = await this.database
            .getRepository(PaymentEntity)
            .findOneBy({ id: paymentId.toLowerCase(), buyerId: buyerId.toLowerCase() });
        if (!payment) return null;
        const [{ now }] = await this.database.query<Array<{ now: Date }>>('SELECT clock_timestamp() AS now');
        const refund = await this.database.getRepository(RefundEntity).findOneBy({ paymentId: payment.id });
        return {
            paymentId: payment.id,
            orderId: payment.orderId,
            status: payment.status,
            amountCents: payment.amountCents,
            currency: payment.currency,
            reservationActive: now < payment.reservationExpiresAt,
            refundStatus: refund?.providerStatus ?? null,
            reference: payment.stripePaymentIntentId
                ? {
                      id: payment.stripePaymentIntentId,
                      paymentId: payment.id,
                      orderId: payment.orderId,
                      buyerId: payment.buyerId,
                      reservationId: payment.reservationId,
                      amountCents: payment.amountCents,
                      currency: payment.currency,
                  }
                : null,
        };
    }
}
