import { Injectable, type OnApplicationShutdown } from '@nestjs/common';
import { DataSource } from 'typeorm';

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
            await this.database.query('SELECT 1');
            return true;
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
