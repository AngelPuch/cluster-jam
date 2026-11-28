import 'reflect-metadata';
import { randomUUID } from 'node:crypto';
import { DataSource } from 'typeorm';
import { createDatabaseOptions } from '../src/infrastructure/database/typeorm.options';
import { PaymentEntity } from '../src/infrastructure/database/entities/payment.entity';
import { RefundEntity } from '../src/infrastructure/database/entities/refund.entity';
import { InboxEntity } from '../src/infrastructure/database/entities/inbox.entity';
import { DatabaseReadiness } from '../src/infrastructure/database/database-readiness.service';
import { verifyEnablePayment } from './verify-enable-payment';
import { verifyRabbitMq } from './verify-rabbitmq';

const describeDatabase = process.env.PAYMENTS_VERIFY_POSTGRES === 'true' ? describe : describe.skip;

describeDatabase('Payments schema on disposable PostgreSQL', () => {
    it('applies once, preserves integer cents and rejects duplicate or partial financial operations', async () => {
        if (
            !['127.0.0.1', 'localhost'].includes(process.env.DB_HOST ?? '') ||
            !/^payments_test_[a-z0-9_]+$/.test(process.env.DB_NAME ?? '') ||
            !process.env.PAYMENTS_MIGRATION_PASSWORD
        ) {
            throw new Error('Use an explicitly enabled local payments_test_* database.');
        }
        const base = { ...process.env, APP_ENV: 'test', DB_SSL: false };
        const migrator = new DataSource(
            createDatabaseOptions({
                ...base,
                DB_USER: 'migrator_pagos',
                DB_PASSWORD: process.env.PAYMENTS_MIGRATION_PASSWORD,
            }),
        );
        const runtime = new DataSource(createDatabaseOptions({ ...base, DB_USER: 'app_pagos' }));
        try {
            await runtime.initialize();
            const readiness = new DatabaseReadiness(runtime);
            expect(await readiness.check()).toBe(false);
            await migrator.initialize();
            expect(await migrator.runMigrations()).toHaveLength(2);
            expect(await migrator.runMigrations()).toHaveLength(0);
            expect(await readiness.check()).toBe(true);
            const payments = runtime.getRepository(PaymentEntity);
            const payment = await payments.save(
                payments.create({
                    id: randomUUID(),
                    orderId: randomUUID(),
                    buyerId: randomUUID(),
                    reservationId: randomUUID(),
                    reservationExpiresAt: new Date(Date.now() + 900000),
                    amountCents: 19900,
                    currency: 'MXN',
                }),
            );
            expect((await payments.findOneByOrFail({ id: payment.id })).amountCents).toBe(19900);
            await expect(payments.save(payments.create({ ...payment, id: randomUUID() }))).rejects.toMatchObject({
                code: '23505',
            });
            const refunds = runtime.getRepository(RefundEntity);
            await expect(
                refunds.save(
                    refunds.create({
                        id: randomUUID(),
                        paymentId: payment.id,
                        amountCents: 100,
                        currency: 'MXN',
                        reason: 'Invalid partial refund',
                    }),
                ),
            ).rejects.toMatchObject({ code: '23503' });
            const refund = await refunds.save(
                refunds.create({
                    id: randomUUID(),
                    paymentId: payment.id,
                    amountCents: payment.amountCents,
                    currency: 'MXN',
                    reason: 'Full compensation',
                }),
            );
            await expect(refunds.save(refunds.create({ ...refund, id: randomUUID() }))).rejects.toMatchObject({
                code: '23505',
            });
            const inbox = runtime.getRepository(InboxEntity);
            const messageId = randomUUID();
            await inbox.insert({ consumer: 'enable-payment', messageId });
            await expect(inbox.insert({ consumer: 'enable-payment', messageId })).rejects.toMatchObject({
                code: '23505',
            });
            await inbox.insert({ consumer: 'stripe-webhook', messageId: 'evt_test_' + randomUUID() });
            await expect(runtime.query('CREATE TABLE app.forbidden_runtime_ddl(id integer)')).rejects.toMatchObject({
                code: '42501',
            });
            await verifyEnablePayment(runtime);
            if (process.env.PAYMENTS_VERIFY_RABBITMQ === 'true') await verifyRabbitMq(runtime);
        } finally {
            if (runtime.isInitialized) await runtime.destroy();
            if (migrator.isInitialized) await migrator.destroy();
        }
    }, 30000);
});
