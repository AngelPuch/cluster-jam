import type { MigrationInterface, QueryRunner } from 'typeorm';
export const PAYMENTS_SCHEMA_VERSION = 1795824000000;
export const PAYMENTS_MIGRATION_NAME = 'RecordRefundCreation1795824000000';
export class RecordRefundCreation1795824000000 implements MigrationInterface {
    name = PAYMENTS_MIGRATION_NAME;
    async up(runner: QueryRunner): Promise<void> {
        await runner.query('ALTER TABLE app.reembolso ADD stripe_creacion_iniciada_en timestamptz');
    }
    async down(runner: QueryRunner): Promise<void> {
        await runner.query('ALTER TABLE app.reembolso DROP COLUMN stripe_creacion_iniciada_en');
    }
}
