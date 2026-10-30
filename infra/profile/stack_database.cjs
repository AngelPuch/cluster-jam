// Runs inside the actual runtime container, using only its mounted app credential.
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { Client } = require(require.resolve('pg', { paths: ['/app'] }));
const config = {
    host: 'db-profile',
    port: 5432,
    user: 'app_profile',
    database: 'profile_db',
    password: readFileSync('/run/secrets/profile_db_password', 'utf8').trim(),
    connectionTimeoutMillis: 3000,
    ssl: { rejectUnauthorized: true, ca: readFileSync('/run/config/profile-db-ca.crt') },
};
async function denied(options) {
    const client = new Client(options);
    try {
        await assert.rejects(client.connect());
    } finally {
        await client.end().catch(() => {});
    }
}
async function main() {
    const client = new Client(config);
    await client.connect();
    try {
        assert.equal((await client.query('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()')).rows[0].ssl, true);
        for (const sql of [
            'CREATE TABLE app.forbidden_probe (id integer)',
            'SELECT * FROM public.migrations',
            'DELETE FROM app.profile WHERE false',
            'DELETE FROM app.inbox_messages WHERE false',
        ])
            await assert.rejects(client.query(sql), (error) => error.code === '42501');
        const counts = (
            await client.query(
                'SELECT (SELECT count(*)::int FROM app.profile) AS profiles, (SELECT count(*)::int FROM app.address) AS addresses, (SELECT count(*)::int FROM app.inbox_messages) AS events',
            )
        ).rows[0];
        assert.deepEqual(counts, { profiles: 2, addresses: 1, events: 3 });
    } finally {
        await client.end();
    }
    await denied({ ...config, ssl: false });
    await denied({ ...config, database: 'postgres' });
    process.stdout.write(
        JSON.stringify({
            checks: [
                'verified-database-tls',
                'runtime-no-ddl-metadata-or-destructive-profile-inbox-grants',
                'runtime-cannot-connect-other-database',
                'plaintext-database-denied',
                'persistent-counts-and-inbox-deduplication',
            ],
        }) + '\n',
    );
}
main().catch(() => {
    process.stderr.write('Profile runtime database verification failed.\n');
    process.exitCode = 1;
});
