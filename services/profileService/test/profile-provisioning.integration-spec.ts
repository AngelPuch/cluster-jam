import { randomUUID } from 'node:crypto';
import { DataSource, type MigrationInterface } from 'typeorm';
import { Test } from '@nestjs/testing';
import { CreateMinimumProfileService } from '../src/application/profile/create-minimum-profile.service';
import type { MinimumProfileInput } from '../src/application/ports/profile-provisioning.port';
import { AddressEntity } from '../src/infrastructure/database/entities/address.entity';
import { InboxMessageEntity } from '../src/infrastructure/database/entities/inbox-message.entity';
import { ProfileEntity, OnboardingStatus } from '../src/infrastructure/database/entities/profile.entity';
import { CreateAccounts1789608835902 } from '../src/infrastructure/database/migrations/1789608835902-create-accounts';
import { UpdateProfile1789964255801 } from '../src/infrastructure/database/migrations/1789964255801-update-profile';
import { AddInboxAndOnboardingStatus1793232000000 } from '../src/infrastructure/database/migrations/1793232000000-add-inbox-and-onboarding-status';
import { TypeormProfileProvisioningAdapter } from '../src/infrastructure/database/repositories/typeorm-profile-provisioning.adapter';
import { ProfileModule } from '../src/profile.module';

const migrations = [CreateAccounts1789608835902, UpdateProfile1789964255801, AddInboxAndOnboardingStatus1793232000000];

describe('Profile migrations and Transactional Inbox with real PostgreSQL', () => {
    let admin: DataSource;
    let database: DataSource;
    let service: CreateMinimumProfileService;
    const databases = new Map<string, DataSource>();

    beforeAll(async () => {
        const url = new URL(process.env.PROFILE_TEST_DATABASE_URL ?? '');
        if (
            process.env.PROFILE_INTEGRATION_LOCAL !== 'true' ||
            !['localhost', '127.0.0.1'].includes(url.hostname) ||
            !['postgres:', 'postgresql:'].includes(url.protocol)
        )
            throw new Error('Provide an explicitly authorized local PostgreSQL test instance.');
        admin = new DataSource({ type: 'postgres', url: url.toString(), synchronize: false });
        await admin.initialize();
        database = await createDatabase(migrations);
        await database.runMigrations();
        service = new CreateMinimumProfileService(new TypeormProfileProvisioningAdapter(database));
    });

    afterAll(async () => {
        for (const [name, source] of databases) {
            if (source.isInitialized) await source.destroy();
            if (!/^profile_test_[a-f0-9]{32}$/.test(name)) throw new Error('Unsafe test database name');
            await admin.query(`DROP DATABASE "${name}" WITH (FORCE)`);
        }
        if (admin?.isInitialized) await admin.destroy();
    });

    async function createDatabase(versions: Array<new () => MigrationInterface>): Promise<DataSource> {
        const name = `profile_test_${randomUUID().replaceAll('-', '')}`;
        const url = new URL(process.env.PROFILE_TEST_DATABASE_URL!);
        url.pathname = `/${name}`;
        await admin.query(`CREATE DATABASE "${name}"`);
        const source = new DataSource({
            type: 'postgres',
            url: url.toString(),
            entities: [ProfileEntity, AddressEntity, InboxMessageEntity],
            migrations: versions,
            migrationsTransactionMode: 'all',
            synchronize: false,
            installExtensions: false,
            logging: false,
        });
        databases.set(name, source);
        await source.initialize();
        return source;
    }

    function event(userId = randomUUID()): MinimumProfileInput {
        return { eventId: randomUUID(), userId, initialContactEmail: 'initial@example.com' };
    }

    it('runs all migrations from empty, with no pending migrations on repetition', async () => {
        expect(await database.showMigrations()).toBe(false);
        await expect(database.runMigrations()).resolves.toEqual([]);
        const columns = await database.query<Array<{ data_type: string; character_maximum_length: number }>>(`
            SELECT data_type, character_maximum_length FROM information_schema.columns
            WHERE table_schema = 'app' AND table_name = 'profile' AND column_name = 'onboarding_status'
        `);
        expect(columns).toEqual([{ data_type: 'character varying', character_maximum_length: 20 }]);
    });

    it('creates a PENDING profile and inbox entry together, without an address', async () => {
        const input = event();
        await expect(service.execute(input)).resolves.toEqual({ status: 'processed', profileCreated: true });
        expect(await database.getRepository(ProfileEntity).findOneByOrFail({ userId: input.userId })).toMatchObject({
            name: null,
            phone: null,
            contactEmail: input.initialContactEmail,
            onboardingStatus: OnboardingStatus.PENDING,
        });
        expect(
            await database.getRepository(InboxMessageEntity).findOneByOrFail({ eventId: input.eventId }),
        ).toMatchObject({
            eventType: 'identity.user.registered',
            processedAt: expect.any(Date) as Date,
        });
        expect(await database.getRepository(AddressEntity).countBy({ userId: input.userId })).toBe(0);
    });

    it('acknowledgeable completion is returned only after another connection sees committed data', async () => {
        const input = event();
        await service.execute(input);
        const runner = database.createQueryRunner();
        try {
            await runner.connect();
            const rows = await runner.manager.query<Array<{ count: string }>>(
                'SELECT count(*) FROM app.inbox_messages WHERE event_id = $1',
                [input.eventId],
            );
            expect(rows[0].count).toBe('1');
        } finally {
            await runner.release();
        }
    });

    it('deduplicates the same event without modifying the existing profile', async () => {
        const input = event();
        await service.execute(input);
        const before = await database.getRepository(ProfileEntity).findOneByOrFail({ userId: input.userId });
        await expect(service.execute(input)).resolves.toEqual({ status: 'duplicate' });
        expect(await database.getRepository(ProfileEntity).findOneByOrFail({ userId: input.userId })).toEqual(before);
        expect(await database.getRepository(InboxMessageEntity).countBy({ eventId: input.eventId })).toBe(1);
    });

    it('does not overwrite completed data for a different event with the same user', async () => {
        const input = event();
        await service.execute(input);
        await database.getRepository(ProfileEntity).update(
            { userId: input.userId },
            {
                name: 'Existing Customer',
                phone: '5551234567',
                contactEmail: 'changed@example.com',
                onboardingStatus: OnboardingStatus.COMPLETED,
            },
        );
        const before = await database.getRepository(ProfileEntity).findOneByOrFail({ userId: input.userId });
        await expect(service.execute({ ...input, eventId: randomUUID() })).resolves.toEqual({
            status: 'processed',
            profileCreated: false,
        });
        expect(await database.getRepository(ProfileEntity).findOneByOrFail({ userId: input.userId })).toEqual(before);
        await expect(service.execute(input)).resolves.toEqual({ status: 'duplicate' });
        expect(await database.getRepository(ProfileEntity).findOneByOrFail({ userId: input.userId })).toEqual(before);
    });

    it('rolls back the inbox if profile insertion fails, allowing the same event to succeed later', async () => {
        const input = event();
        await expect(service.execute({ ...input, initialContactEmail: 'x'.repeat(255) })).rejects.toThrow();
        expect(await database.getRepository(InboxMessageEntity).countBy({ eventId: input.eventId })).toBe(0);
        expect(await database.getRepository(ProfileEntity).countBy({ userId: input.userId })).toBe(0);
        await expect(service.execute(input)).resolves.toEqual({ status: 'processed', profileCreated: true });
    });

    it('enforces uniqueness during concurrent delivery of the same event', async () => {
        const input = event();
        const results = await Promise.all(Array.from({ length: 8 }, () => service.execute(input)));
        expect(results.filter((result) => result.status === 'processed')).toHaveLength(1);
        expect(results.filter((result) => result.status === 'duplicate')).toHaveLength(7);
        expect(await database.getRepository(ProfileEntity).countBy({ userId: input.userId })).toBe(1);
        expect(await database.getRepository(InboxMessageEntity).countBy({ eventId: input.eventId })).toBe(1);
    });

    it('enforces uniqueness for concurrent different events targeting one user', async () => {
        const userId = randomUUID();
        const inputs = Array.from({ length: 8 }, () => event(userId));
        const results = await Promise.all(inputs.map((input) => service.execute(input)));
        expect(results.filter((result) => result.status === 'processed' && result.profileCreated)).toHaveLength(1);
        expect(await database.getRepository(ProfileEntity).countBy({ userId })).toBe(1);
        for (const input of inputs)
            expect(await database.getRepository(InboxMessageEntity).countBy({ eventId: input.eventId })).toBe(1);
    });

    it('rejects invalid states and missing contact email at the database boundary', async () => {
        await expect(
            database.query(
                `INSERT INTO app.profile (user_id, contact_email, onboarding_status) VALUES ($1, $2, 'INVALID')`,
                [randomUUID(), 'initial@example.com'],
            ),
        ).rejects.toThrow();
        await expect(database.query('INSERT INTO app.profile (user_id) VALUES ($1)', [randomUUID()])).rejects.toThrow();
    });

    it('upgrades populated first-migration schemas without inventing contact data', async () => {
        const source = await createDatabase([CreateAccounts1789608835902]);
        await source.runMigrations();
        const userId = randomUUID();
        await source.query('INSERT INTO app.profile (user_id, name, phone) VALUES ($1, $2, $3)', [
            userId,
            'Legacy Customer',
            '5551234567',
        ]);
        source.setOptions({ migrations });
        await source.destroy();
        await source.initialize();
        await source.runMigrations();
        expect(await source.getRepository(ProfileEntity).findOneByOrFail({ userId })).toMatchObject({
            name: 'Legacy Customer',
            phone: '5551234567',
            contactEmail: null,
            onboardingStatus: OnboardingStatus.PENDING,
        });
    });

    it('preserves completed profiles and recognizes complete legacy profiles on upgrade', async () => {
        const source = await createDatabase([CreateAccounts1789608835902, UpdateProfile1789964255801]);
        await source.runMigrations();
        const completed = randomUUID();
        const legacyComplete = randomUUID();
        for (const [userId, status] of [
            [completed, 'COMPLETED'],
            [legacyComplete, 'PENDING'],
        ]) {
            await source.query(
                `INSERT INTO app.profile (user_id, name, phone, contact_email, onboarding_status) VALUES ($1, $2, $3, $4, $5)`,
                [userId, 'Existing Customer', '5551234567', 'customer@example.com', status],
            );
        }
        source.setOptions({ migrations });
        await source.destroy();
        await source.initialize();
        await source.runMigrations();
        for (const userId of [completed, legacyComplete]) {
            expect(await source.getRepository(ProfileEntity).findOneByOrFail({ userId })).toMatchObject({
                onboardingStatus: OnboardingStatus.COMPLETED,
                contactEmail: 'customer@example.com',
            });
        }
        await source.undoLastMigration();
        expect(await source.getRepository(ProfileEntity).findOneByOrFail({ userId: completed })).toMatchObject({
            onboardingStatus: OnboardingStatus.COMPLETED,
        });
        await expect(source.runMigrations()).resolves.toHaveLength(1);
    });

    it('wires the actual Nest module to the persistence adapter', async () => {
        process.env.DB_HOST = '127.0.0.1';
        process.env.DB_USER = 'profile_test';
        process.env.DB_PASSWORD = 'test-only';
        process.env.DB_NAME = 'unused-override';
        const module = await Test.createTestingModule({ imports: [ProfileModule] })
            .overrideProvider(DataSource)
            .useValue(database)
            .compile();
        try {
            await expect(module.get(CreateMinimumProfileService).execute(event())).resolves.toMatchObject({
                status: 'processed',
                profileCreated: true,
            });
        } finally {
            // This is the last test; Nest closes its overridden connection.
            await module.close();
        }
    });
});
