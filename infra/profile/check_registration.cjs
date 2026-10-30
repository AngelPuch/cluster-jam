// One focused acceptance flow, using both real compiled applications and local Supabase.
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const { randomUUID } = require('node:crypto');
const { resolve } = require('node:path');
const root = resolve(__dirname, '../..');
const profileRequire = createRequire(resolve(root, 'services/profileService/package.json'));
const authRequire = createRequire(resolve(root, 'services/authService/package.json'));
const { Pool } = profileRequire('pg');
const { DataSource } = profileRequire('typeorm');
const { NestFactory: ProfileFactory } = profileRequire('@nestjs/core');
const { NestFactory: AuthFactory } = authRequire('@nestjs/core');
const amqp = profileRequire('amqplib');
let stage = 'local configuration';

async function main() {
    if (process.env.PROFILE_REGISTRATION_LOCAL !== 'true') throw new Error('Explicit local acceptance required.');
    const supabase = new URL(process.env.SUPABASE_URL);
    const supabaseDb = new URL(process.env.PROFILE_REGISTRATION_SUPABASE_DB);
    const profileDb = new URL(process.env.PROFILE_TEST_DATABASE_URL);
    const broker = new URL(process.env.PROFILE_TEST_RABBITMQ_URI);
    for (const url of [supabase, supabaseDb, profileDb, broker])
        assert(['localhost', '127.0.0.1'].includes(url.hostname), 'Dependencies must be loopback-only.');
    const name = 'profile_test_' + randomUUID().replaceAll('-', '');
    const role = 'profile_acceptance_' + randomUUID().replaceAll('-', '').slice(0, 16);
    const rolePassword = randomUUID().replaceAll('-', '');
    const admin = new Pool({ connectionString: supabaseDb.toString(), connectionTimeoutMillis: 5000 });
    const profilesAdmin = new Pool({ connectionString: profileDb.toString(), connectionTimeoutMillis: 5000 });
    let migration;
    let auth;
    let profile;
    let userId;
    let createdDatabase = false;
    let createdRole = false;
    try {
        stage = 'real Supabase migration and publisher role';
        assert.equal(
            (await admin.query('SELECT count(*)::int AS count FROM auth.users')).rows[0].count,
            0,
            'Use a fresh disposable Supabase project.',
        );
        assert((await admin.query("SELECT to_regclass('integration.auth_outbox') AS name")).rows[0].name);
        const createRole = await admin.query(
            "SELECT format('CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', $1::text, $2::text) AS sql",
            [role, rolePassword],
        );
        await admin.query(createRole.rows[0].sql);
        createdRole = true;
        await admin.query(`GRANT auth_outbox_publisher TO "${role}"`);
        const publisherDb = new URL(supabaseDb);
        publisherDb.username = role;
        publisherDb.password = rolePassword;
        publisherDb.search = '';
        await profilesAdmin.query(`CREATE DATABASE "${name}"`);
        createdDatabase = true;
        Object.assign(process.env, {
            APP_ENV: 'test',
            HTTP_PORT: '8080',
            LOG_LEVEL: 'ERROR',
            DB_HOST: profileDb.hostname,
            DB_PORT: profileDb.port || '5432',
            DB_USER: decodeURIComponent(profileDb.username),
            DB_PASSWORD: decodeURIComponent(profileDb.password),
            DB_NAME: name,
            DB_SSL: 'false',
            DB_PASSWORD_FILE: '',
            SUPABASE_JWKS_URL: supabase.origin + '/auth/v1/.well-known/jwks.json',
            SUPABASE_PUBLISHABLE_KEY_FILE: '',
            OUTBOX_DATABASE_URL: publisherDb.toString(),
            OUTBOX_DATABASE_URL_FILE: '',
            OUTBOX_DATABASE_SSL: 'false',
            OUTBOX_PUBLISHER_ENABLED: 'true',
            RABBITMQ_URI: broker.toString(),
            RABBITMQ_URL: broker.toString(),
            RABBITMQ_URI_FILE: '',
            RABBITMQ_URL_FILE: '',
            RABBITMQ_CONSUMER_ENABLED: 'true',
        });
        stage = 'real Profile schema and broker topology';
        const { createDatabaseOptions } = profileRequire('./dist/infrastructure/database/typeorm.options.js');
        migration = new DataSource(createDatabaseOptions());
        await migration.initialize();
        await migration.runMigrations();
        await migration.destroy();
        const connection = await amqp.connect(broker.toString());
        try {
            const channel = await connection.createChannel();
            await channel.assertExchange('identity.events', 'topic', { durable: true });
            await channel.close();
        } finally {
            await connection.close();
        }
        const { AppModule: ProfileModule } = profileRequire('./dist/app.module.js');
        profile = await ProfileFactory.create(ProfileModule, { logger: false, abortOnError: false });
        await profile.init();
        const { RabbitMqListener } = profileRequire('./dist/infrastructure/messaging/rabbitmq-listener.js');
        for (let attempt = 0; !profile.get(RabbitMqListener).isReady && attempt < 100; attempt++)
            await new Promise((resolveWait) => setTimeout(resolveWait, 100));
        assert(profile.get(RabbitMqListener).isReady);
        stage = 'real Auth application';
        const { AppModule: AuthModule } = authRequire('./dist/app.module.js');
        const { configureHttpApplication } = authRequire('./dist/interfaces/http/http.setup.js');
        auth = await AuthFactory.create(AuthModule, { logger: false, abortOnError: false });
        configureHttpApplication(auth);
        await auth.listen(0, '127.0.0.1');
        stage = 'HTTP registration in Auth and Supabase';
        const email = 'school-profile-' + randomUUID() + '@example.com';
        const response = await fetch((await auth.getUrl()) + '/api/v1/registrations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password: 'School-' + randomUUID() + '-Ab1!' }),
            signal: AbortSignal.timeout(15000),
        });
        assert.equal(response.status, 201);
        const registration = await response.json();
        userId = registration.userId;
        assert.match(userId, /^[a-f0-9-]{36}$/);
        assert.equal(registration.status, 'PENDING_EMAIL_CONFIRMATION');
        stage = 'trigger, confirmed outbox publication and Profile persistence';
        const actualProfiles = profile.get(DataSource);
        let state;
        for (let attempt = 0; attempt < 150; attempt++) {
            const outbox = await admin.query(
                'SELECT id, publicado_en FROM integration.auth_outbox WHERE agregado_id=$1',
                [userId],
            );
            const rows = await actualProfiles.query(
                'SELECT user_id, name, phone, contact_email, onboarding_status FROM app.profile WHERE user_id=$1',
                [userId],
            );
            if (outbox.rows[0]?.publicado_en && rows.length === 1) {
                state = { event: outbox.rows[0], profile: rows[0] };
                break;
            }
            await new Promise((resolveWait) => setTimeout(resolveWait, 200));
        }
        assert(state, 'Registration event did not reach Profile.');
        assert.deepEqual(state.profile, {
            user_id: userId,
            name: null,
            phone: null,
            contact_email: email,
            onboarding_status: 'PENDING',
        });
        assert.equal(
            (
                await actualProfiles.query('SELECT count(*)::int AS count FROM app.inbox_messages WHERE event_id=$1', [
                    state.event.id,
                ])
            )[0].count,
            1,
        );
        assert.equal(
            (await actualProfiles.query('SELECT count(*)::int AS count FROM app.address WHERE user_id=$1', [userId]))[0]
                .count,
            0,
        );
        assert.equal(
            (await admin.query("SELECT raw_app_meta_data->>'app_role' AS role FROM auth.users WHERE id=$1", [userId]))
                .rows[0].role,
            'cliente',
        );
        process.stdout.write(
            'PASS: real Auth signup -> Supabase trigger/outbox -> RabbitMQ -> minimum Profile (one acceptance scenario).\n',
        );
    } finally {
        await auth?.close();
        await profile?.close();
        if (migration?.isInitialized) await migration.destroy();
        if (userId) {
            await admin.query('DELETE FROM integration.auth_outbox WHERE agregado_id=$1', [userId]);
            await admin.query('DELETE FROM auth.users WHERE id=$1', [userId]);
        }
        if (createdRole) await admin.query(`DROP ROLE "${role}"`);
        if (createdDatabase) {
            if (!/^profile_test_[a-f0-9]{32}$/.test(name)) throw new Error('Unsafe cleanup database name.');
            await profilesAdmin.query(`DROP DATABASE "${name}" WITH (FORCE)`);
        }
        await admin.end();
        await profilesAdmin.end();
    }
}
main().catch(() => {
    process.stderr.write(
        'Registration acceptance failed at: ' + stage + '. No credentials or submitted fields were logged.\n',
    );
    process.exit(1);
});
