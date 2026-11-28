import { randomUUID } from 'node:crypto';
import type { DataSource } from 'typeorm';
import { CancelPaymentService } from '../src/application/payments/cancel-payment.service';
import { EnablePaymentService } from '../src/application/payments/enable-payment.service';
import { PaymentCommandConflict } from '../src/application/payments/payment.error';
import {
    PaymentMessageType,
    type CancelPayment,
    type EnablePayment,
} from '../src/application/payments/payment-messages';
import { DatabaseReadiness } from '../src/infrastructure/database/database-readiness.service';
import { PaymentEntity } from '../src/infrastructure/database/entities/payment.entity';
import { OutboxEntity } from '../src/infrastructure/database/entities/outbox.entity';
import { InboxEntity } from '../src/infrastructure/database/entities/inbox.entity';
import { TypeormEnablePaymentStore } from '../src/infrastructure/database/typeorm-enable-payment.store';
import { TypeormCancelPaymentStore } from '../src/infrastructure/database/typeorm-cancel-payment.store';
import { StripeCancelGateway } from '../src/infrastructure/stripe/stripe-cancel.gateway';
import { StripeIntentGateway } from '../src/infrastructure/stripe/stripe-intent.gateway';
import { StripeFixture } from './stripe-fixture';
export async function verifyCancellation(database: DataSource): Promise<void> {
    const fixture = new StripeFixture();
    try {
        const stripe = await fixture.open();
        const ready = new DatabaseReadiness(database);
        const enable = new EnablePaymentService(
            new TypeormEnablePaymentStore(database, ready),
            new StripeIntentGateway(stripe),
        );
        const cancel = new CancelPaymentService(
            new TypeormCancelPaymentStore(database, ready),
            new StripeCancelGateway(stripe),
        );
        const payments = database.getRepository(PaymentEntity);
        const outbox = database.getRepository(OutboxEntity);
        async function prepared(): Promise<CancelPayment> {
            const command: EnablePayment = {
                messageId: randomUUID(),
                orderId: randomUUID(),
                type: PaymentMessageType.Enable,
                occurredAt: new Date().toISOString(),
                data: {
                    buyerId: randomUUID(),
                    reservationId: randomUUID(),
                    reservationExpiresAt: new Date(Date.now() + 900000).toISOString(),
                    amountCents: 19900,
                    currency: 'MXN',
                },
            };
            await enable.execute(command);
            const payment = await payments.findOneByOrFail({ orderId: command.orderId });
            return {
                ...command,
                type: PaymentMessageType.Cancel,
                messageId: randomUUID(),
                data: { paymentId: payment.id, reason: 'Checkout cancelled' },
            };
        }
        const first = await prepared();
        fixture.dropCancelResponses = 2;
        await cancel.execute(first);
        await cancel.execute(first);
        await cancel.execute({ ...first, messageId: randomUUID() });
        expect((await payments.findOneByOrFail({ id: first.data.paymentId })).status).toBe('CANCELADO');
        expect(fixture.cancelEffects).toBe(1);
        const results = (await outbox.find()).filter((event) => event.body.orderId === first.orderId);
        expect(results.filter((event) => event.routingKey === String(PaymentMessageType.NotCompleted))).toHaveLength(1);
        expect(
            await database.getRepository(InboxEntity).existsBy({ consumer: first.type, messageId: first.messageId }),
        ).toBe(true);
        const paid = await prepared();
        fixture.succeedOnNextCancel = true;
        await cancel.execute(paid);
        await cancel.execute({ ...paid, messageId: randomUUID() });
        expect((await payments.findOneByOrFail({ id: paid.data.paymentId })).status).toBe('PAGADO');
        const paidResults = (await outbox.find()).filter((event) => event.body.orderId === paid.orderId);
        expect(paidResults.filter((event) => event.routingKey === String(PaymentMessageType.Succeeded))).toHaveLength(
            1,
        );
        expect(
            paidResults.filter((event) => event.routingKey === String(PaymentMessageType.NotCompleted)),
        ).toHaveLength(0);
        await expect(
            cancel.execute({ ...paid, orderId: randomUUID(), messageId: randomUUID() }),
        ).rejects.toBeInstanceOf(PaymentCommandConflict);
    } finally {
        await fixture.close();
    }
}
