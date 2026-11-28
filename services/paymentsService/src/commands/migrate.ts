import { existsSync } from 'node:fs';
import { loadEnvFile } from 'node:process';
import { DataSource } from 'typeorm';
import { createDatabaseOptions } from '../infrastructure/database/typeorm.options';
import { JsonLogger } from '../infrastructure/observability/json-logger.service';

async function run(): Promise<void> {
    if (existsSync('.env')) loadEnvFile('.env');
    const password = process.env.PAYMENTS_MIGRATION_PASSWORD;
    if (!password?.trim()) throw new Error('Missing migration configuration.');
    const database = new DataSource(
        createDatabaseOptions({ ...process.env, DB_USER: 'migrator_pagos', DB_PASSWORD: password }),
    );
    try {
        await database.initialize();
        await database.runMigrations();
        new JsonLogger().log({ event: 'payments.migrations.applied' });
    } finally {
        if (database.isInitialized) await database.destroy();
    }
}

void run().catch(() => {
    new JsonLogger().error({ event: 'payments.migrations.failed' });
    process.exitCode = 1;
});
