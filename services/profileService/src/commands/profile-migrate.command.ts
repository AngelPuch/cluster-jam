import type { DataSource } from 'typeorm';
import { JsonLogger } from '../infrastructure/observability/json-logger.service';

async function run(): Promise<void> {
    const logger = new JsonLogger();
    let source: DataSource | undefined;
    try {
        const { AppDataSource } = await import('../infrastructure/database/typeorm.config.js');
        source = AppDataSource;
        await source.initialize();
        await source.runMigrations();
        const role = process.env.DB_RUNTIME_ROLE;
        if (role !== undefined) {
            if (!/^[a-z_][a-z0-9_]{0,62}$/.test(role)) throw new Error('Invalid runtime role.');
            await source.transaction(async (manager) => {
                await manager.query(`GRANT USAGE ON SCHEMA app TO "${role}"`);
                await manager.query(`GRANT SELECT, INSERT, UPDATE ON app.profile TO "${role}"`);
                await manager.query(`GRANT SELECT, INSERT, UPDATE, DELETE ON app.address TO "${role}"`);
                await manager.query(`GRANT SELECT, INSERT ON app.inbox_messages TO "${role}"`);
            });
        }
        logger.log({ event: 'profile.migrations.applied' });
    } catch {
        logger.error({ event: 'profile.migrations.failed' });
        process.exitCode = 1;
    } finally {
        if (source?.isInitialized) await source.destroy();
    }
}
void run().catch(() => {
    new JsonLogger().error({ event: 'profile.migrations.failed' });
    process.exitCode = 1;
});
