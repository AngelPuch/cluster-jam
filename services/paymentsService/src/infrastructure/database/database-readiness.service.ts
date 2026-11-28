import { Injectable, type OnApplicationShutdown } from '@nestjs/common';
import { DataSource } from 'typeorm';
import { PAYMENTS_MIGRATION_NAME, PAYMENTS_SCHEMA_VERSION } from './migrations/1795741200000-record-stripe-creation';

@Injectable()
export class DatabaseReadiness implements OnApplicationShutdown {
    private opening?: Promise<DataSource>;
    private stopping = false;

    constructor(private readonly database: DataSource) {}

    async check(): Promise<boolean> {
        if (this.stopping) return false;
        try {
            if (!this.database.isInitialized) {
                this.opening ??= this.database.initialize().finally(() => {
                    this.opening = undefined;
                });
                await this.opening;
            }
            if (this.stopping) return false;
            const rows = await this.database.query<Array<{ ready: boolean }>>(
                'SELECT EXISTS(SELECT 1 FROM app.migrations_pagos WHERE timestamp = $1 AND name = $2) AS ready',
                [PAYMENTS_SCHEMA_VERSION, PAYMENTS_MIGRATION_NAME],
            );
            return rows[0]?.ready === true;
        } catch {
            return false;
        }
    }

    async onApplicationShutdown(): Promise<void> {
        this.stopping = true;
        await this.opening?.catch(() => undefined);
        if (this.database.isInitialized) await this.database.destroy();
    }
}
