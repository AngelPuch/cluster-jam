import { MigrationInterface, QueryRunner } from 'typeorm';

export class UpdateProfile1789964255801 implements MigrationInterface {
    name = 'UpdateProfile1789964255801';

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(
            `ALTER TABLE "app"."profile" ADD "contact_email" character varying(254) NOT NULL`,
        );
        await queryRunner.query(
            `ALTER TABLE "app"."profile" ADD "onboarding_status" text NOT NULL DEFAULT 'PENDING'`,
        );
        await queryRunner.query(
            `ALTER TABLE "app"."profile" ALTER COLUMN "name" DROP NOT NULL`,
        );
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(
            `ALTER TABLE "app"."profile" ALTER COLUMN "name" SET NOT NULL`,
        );
        await queryRunner.query(
            `ALTER TABLE "app"."profile" DROP COLUMN "onboarding_status"`,
        );
        await queryRunner.query(
            `ALTER TABLE "app"."profile" DROP COLUMN "contact_email"`,
        );
    }
}
