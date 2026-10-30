import type { MigrationInterface, QueryRunner } from 'typeorm';

export class AddInboxAndOnboardingStatus1793232000000 implements MigrationInterface {
    name = 'AddInboxAndOnboardingStatus1793232000000';

    async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`
            ALTER TABLE app.profile
            ALTER COLUMN onboarding_status TYPE varchar(20),
            ALTER COLUMN onboarding_status SET DEFAULT 'PENDING',
            ADD CONSTRAINT "CK_profile_onboarding_status"
                CHECK (onboarding_status IN ('PENDING', 'COMPLETED'))
        `);
        // Legacy profiles without contact email remain readable. New rows and
        // updates must provide it; no credentials or synthetic emails are copied.
        await queryRunner.query(`
            ALTER TABLE app.profile
            ADD CONSTRAINT "CK_profile_contact_email_required"
                CHECK (contact_email IS NOT NULL AND btrim(contact_email) <> '') NOT VALID
        `);
        await queryRunner.query(`
            UPDATE app.profile SET onboarding_status = 'COMPLETED'
            WHERE onboarding_status = 'PENDING'
                AND nullif(btrim(name), '') IS NOT NULL
                AND nullif(btrim(phone), '') IS NOT NULL
                AND contact_email ~ '^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$'
        `);
        await queryRunner.query(`
            CREATE TABLE app.inbox_messages (
                event_id uuid PRIMARY KEY,
                event_type varchar(100) NOT NULL,
                processed_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT "CK_inbox_event_type" CHECK (btrim(event_type) <> '')
            )
        `);
    }

    async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query('DROP TABLE app.inbox_messages');
        await queryRunner.query(`
            ALTER TABLE app.profile
            DROP CONSTRAINT "CK_profile_contact_email_required",
            DROP CONSTRAINT "CK_profile_onboarding_status",
            ALTER COLUMN onboarding_status TYPE text
        `);
        // Preserve onboarding outcomes: rolling back infrastructure must not
        // revert completed customer profiles to PENDING.
    }
}
