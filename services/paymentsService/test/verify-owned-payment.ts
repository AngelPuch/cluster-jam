import { randomUUID } from 'node:crypto';
import type { DataSource } from 'typeorm';
import { PaymentAccessService } from '../src/application/payments/payment-access.service';
import { PaymentStatus } from '../src/application/payments/payment';
import { PaymentNotFound, PaymentNotPayable } from '../src/application/payments/payment-access.error';
import { DatabaseReadiness } from '../src/infrastructure/database/database-readiness.service';
import { TypeormOwnedPaymentStore } from '../src/infrastructure/database/typeorm-owned-payment.store';
import { PaymentEntity } from '../src/infrastructure/database/entities/payment.entity';
export async function verifyOwnedPayment(database: DataSource): Promise<void> {
    const repository = database.getRepository(PaymentEntity);
    const owner = randomUUID();
    const id = randomUUID();
    await repository.insert({
        id,
        buyerId: owner,
        orderId: randomUUID(),
        reservationId: randomUUID(),
        amountCents: 19900,
        currency: 'MXN',
        reservationExpiresAt: new Date(Date.now() + 900000),
        stripePaymentIntentId: 'pi_test' + randomUUID().replaceAll('-', ''),
    });
    const store = new TypeormOwnedPaymentStore(database, new DatabaseReadiness(database));
    let reads = 0;
    const service = new PaymentAccessService(store, {
        clientSecret: () => {
            reads++;
            return Promise.resolve('fixture_client_secret');
        },
    });
    expect(await store.findOwned(id, randomUUID())).toBeNull();
    await expect(service.access(id, randomUUID())).rejects.toBeInstanceOf(PaymentNotFound);
    expect(reads).toBe(0);
    expect(await service.access(id, owner)).toEqual({ paymentId: id, clientSecret: 'fixture_client_secret' });
    await repository.update(id, { reservationExpiresAt: new Date(Date.now() - 60000) });
    await expect(service.access(id, owner)).rejects.toBeInstanceOf(PaymentNotPayable);
    expect(reads).toBe(1);
    expect(await service.summary(id, owner)).toMatchObject({ paymentId: id, status: 'PENDIENTE', amountCents: 19900 });
    await repository.update(id, { reservationExpiresAt: new Date(Date.now() + 900000) });
    const racing = new PaymentAccessService(store, {
        clientSecret: () => repository.update(id, { status: PaymentStatus.Paid }).then(() => 'fixture_client_secret'),
    });
    await expect(racing.access(id, owner)).rejects.toBeInstanceOf(PaymentNotPayable);
}
