import { MigrationInterface, QueryRunner } from 'typeorm';

export class CreateAccounts1789608835902 implements MigrationInterface {
    name = 'CreateAccounts1789608835902';

    public async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`CREATE SCHEMA IF NOT EXISTS "app"`);
        await queryRunner.query(
            `CREATE TABLE "app"."profile" ("user_id" uuid NOT NULL, "name" character varying(120) NOT NULL, "phone" character varying(30), "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), "updated_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), CONSTRAINT "PK_d752442f45f258a8bdefeebb2f2" PRIMARY KEY ("user_id"))`,
        );
        await queryRunner.query(
            `CREATE TABLE "app"."address" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "user_id" uuid NOT NULL, "label" character varying(40) NOT NULL, "recipient" character varying(120) NOT NULL, "street" character varying(160) NOT NULL, "exterior_number" character varying(20) NOT NULL, "interior_number" character varying(20), "neighborhood" character varying(120) NOT NULL, "municipality" character varying(120) NOT NULL, "state" character varying(120) NOT NULL, "postal_code" character varying(5) NOT NULL, "country" character(2) NOT NULL, "is_default" boolean NOT NULL DEFAULT false, CONSTRAINT "PK_d92de1f82754668b5f5f5dd4fd5" PRIMARY KEY ("id"))`,
        );
        await queryRunner.query(
            `CREATE UNIQUE INDEX "UQ_address_default_user" ON "app"."address"  ("user_id") WHERE "is_default" = true`,
        );
        await queryRunner.query(
            `ALTER TABLE "app"."address" ADD CONSTRAINT "FK_35cd6c3fafec0bb5d072e24ea20" FOREIGN KEY ("user_id") REFERENCES "app"."profile"("user_id") ON DELETE NO ACTION ON UPDATE NO ACTION`,
        );
    }

    public async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(
            `ALTER TABLE "app"."address" DROP CONSTRAINT "FK_35cd6c3fafec0bb5d072e24ea20"`,
        );
        await queryRunner.query(`DROP INDEX "app"."UQ_address_default_user"`);
        await queryRunner.query(`DROP TABLE "app"."address"`);
        await queryRunner.query(`DROP TABLE "app"."profile"`);
    }
}
