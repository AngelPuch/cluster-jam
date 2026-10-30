import { validateEnvironment } from './environment.validation';

describe('Profile database configuration', () => {
    const valid = {
        DB_HOST: 'localhost',
        DB_NAME: 'profiles',
        DB_USER: 'profiles',
        DB_PASSWORD: 'test-only',
        RABBITMQ_CONSUMER_ENABLED: false,
        SUPABASE_URL: 'https://supabase.example.test',
        SUPABASE_JWKS_URL: 'https://supabase.example.test/auth/v1/.well-known/jwks.json',
    };

    it('normalizes local defaults and ports', () => {
        expect(validateEnvironment({ ...valid, DB_PORT: '5432' })).toMatchObject({
            DB_PORT: 5432,
            DB_SSL: false,
            HTTP_PORT: 8080,
        });
    });

    it.each(['DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD'])('requires %s without exposing its value', (key) => {
        expect(() => validateEnvironment({ ...valid, [key]: '' })).toThrow(`Invalid configuration: ${key}`);
    });

    it.each(['0', '65536', '1.2', 'invalid'])('rejects invalid ports: %s', (DB_PORT) => {
        expect(() => validateEnvironment({ ...valid, DB_PORT })).toThrow('DB_PORT');
    });

    it.each(['staging', 'production'])('requires verified TLS for %s', (APP_ENV) => {
        expect(() => validateEnvironment({ ...valid, APP_ENV })).toThrow('DB_SSL');
        expect(validateEnvironment({ ...valid, APP_ENV, DB_SSL: 'true' })).toMatchObject({ DB_SSL: true });
    });

    it('rejects invalid environment and boolean values', () => {
        expect(() => validateEnvironment({ ...valid, APP_ENV: 'prod' })).toThrow('APP_ENV');
        expect(() => validateEnvironment({ ...valid, DB_SSL: 'yes' })).toThrow('DB_SSL');
    });
});
