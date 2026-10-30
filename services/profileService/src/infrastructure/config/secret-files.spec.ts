import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { resolveSecretFiles } from './secret-files';
import { validateDatabaseEnvironment, validateEnvironment } from './environment.validation';

describe('Mounted Profile secrets', () => {
    let directory: string;
    beforeEach(() => {
        directory = mkdtempSync(join(tmpdir(), 'profile-secrets-'));
    });
    afterEach(() => {
        const target = resolve(directory);
        if (dirname(target) !== resolve(tmpdir()) || !basename(target).startsWith('profile-secrets-'))
            throw new Error('Unsafe test cleanup path.');
        rmSync(target, { recursive: true, force: true });
    });
    function file(value: string) {
        const path = join(directory, 'secret');
        writeFileSync(path, value);
        return path;
    }
    it('reads a bounded mounted secret, preserves password spaces and leaves inputs unchanged', () => {
        const input = { DB_PASSWORD_FILE: file(' secret-with-spaces \r\n') };
        expect(resolveSecretFiles(input, ['DB_PASSWORD']).DB_PASSWORD).toBe(' secret-with-spaces ');
        expect(input).not.toHaveProperty('DB_PASSWORD');
    });
    it.each(['', '\n', 'one\ntwo', 'one\rtwo', 'zero\0byte', 'x'.repeat(8193)])(
        'rejects an invalid secret %# safely',
        (value) => {
            expect(() => resolveSecretFiles({ DB_PASSWORD_FILE: file(value) }, ['DB_PASSWORD'])).toThrow(
                'Cannot load secret file: DB_PASSWORD',
            );
        },
    );
    it('rejects ambiguous values and missing/non-file mounts without exposing paths or secrets', () => {
        expect(() =>
            resolveSecretFiles({ DB_PASSWORD: 'private-password', DB_PASSWORD_FILE: file('another') }, ['DB_PASSWORD']),
        ).toThrow('Invalid secret configuration: DB_PASSWORD');
        for (const path of [directory, join(directory, 'private-path')])
            expect(() => resolveSecretFiles({ DB_PASSWORD_FILE: path }, ['DB_PASSWORD'])).toThrow(
                'Cannot load secret file: DB_PASSWORD',
            );
    });
    it('keeps migration database validation independent from identity and broker secrets', () => {
        expect(
            validateDatabaseEnvironment({
                DB_HOST: 'localhost',
                DB_USER: 'migration',
                DB_NAME: 'profiles',
                DB_PASSWORD_FILE: file('private-password'),
                RABBITMQ_URI_FILE: join(directory, 'absent'),
            }),
        ).toMatchObject({ DB_PASSWORD: 'private-password' });
    });
    it.each(['app;DROP ROLE app_profile', '', 'Uppercase', 42, 'x'.repeat(64)])(
        'rejects unsafe migration grant role identifiers %# before database use',
        (DB_RUNTIME_ROLE) => {
            expect(() =>
                validateDatabaseEnvironment({
                    DB_HOST: 'localhost',
                    DB_USER: 'migration',
                    DB_NAME: 'profiles',
                    DB_PASSWORD: 'local-test-only',
                    DB_RUNTIME_ROLE,
                }),
            ).toThrow('DB_RUNTIME_ROLE');
        },
    );
    it('resolves a mounted AMQPS URI and still applies production transport validation', () => {
        const base = {
            APP_ENV: 'production',
            DB_SSL: true,
            DB_HOST: 'db',
            DB_USER: 'app',
            DB_NAME: 'profiles',
            DB_PASSWORD: 'local-test-only',
            SUPABASE_URL: 'https://supabase.example.test',
            SUPABASE_JWKS_URL: 'https://supabase.example.test/auth/v1/.well-known/jwks.json',
        };
        expect(
            validateEnvironment({ ...base, RABBITMQ_URI_FILE: file('amqps://profile:test@broker/vhost\n') }),
        ).toMatchObject({ RABBITMQ_URI: 'amqps://profile:test@broker/vhost' });
        expect(() =>
            validateEnvironment({ ...base, RABBITMQ_URI_FILE: file('amqp://profile:test@broker/vhost') }),
        ).toThrow('RABBITMQ_URI');
    });
});
