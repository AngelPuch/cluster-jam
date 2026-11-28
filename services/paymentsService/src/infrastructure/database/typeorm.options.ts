import { readFileSync } from 'node:fs';
import type { DataSourceOptions } from 'typeorm';
import { validateEnvironment } from '../config/environment.validation';
import { PaymentEntity } from './entities/payment.entity';
import { RefundEntity } from './entities/refund.entity';
import { InboxEntity } from './entities/inbox.entity';
import { OutboxEntity } from './entities/outbox.entity';
import { CreatePayments1795737600000 } from './migrations/1795737600000-create-payments';

export function createDatabaseOptions(input: Record<string, unknown> = process.env): DataSourceOptions {
    const config = validateEnvironment(input);
    const caPath = typeof config.DB_CA_PATH === 'string' ? config.DB_CA_PATH : undefined;
    return {
        type: 'postgres',
        host: String(config.DB_HOST),
        port: Number(config.DB_PORT),
        database: String(config.DB_NAME),
        username: String(config.DB_USER),
        password: String(config.DB_PASSWORD),
        ssl: config.DB_SSL
            ? { rejectUnauthorized: true, ...(caPath ? { ca: readFileSync(caPath, 'utf8') } : {}) }
            : false,
        schema: 'app',
        entities: [PaymentEntity, RefundEntity, InboxEntity, OutboxEntity],
        migrations: [CreatePayments1795737600000],
        migrationsTableName: 'migrations_pagos',
        migrationsTransactionMode: 'all',
        synchronize: false,
        migrationsRun: false,
        installExtensions: false,
        logging: false,
        poolSize: 5,
        extra: { connectionTimeoutMillis: 3000, statement_timeout: 3000 },
    };
}
