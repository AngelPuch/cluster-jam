import type { MigrationInterface, QueryRunner } from 'typeorm';

export const PAYMENTS_SCHEMA_VERSION = 1795741200000;
export const PAYMENTS_MIGRATION_NAME = 'RecordStripeCreation1795741200000';

export class RecordStripeCreation1795741200000 implements MigrationInterface {
    name = PAYMENTS_MIGRATION_NAME;
    async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query('ALTER TABLE app.pago ADD stripe_creacion_iniciada_en timestamptz');
    }
    async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query('ALTER TABLE app.pago DROP COLUMN stripe_creacion_iniciada_en');
    }
}
