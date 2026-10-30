import { validateEnvironment } from './environment.validation';

describe('RabbitMQ environment contract', () => {
    const valid = {
        DB_HOST: 'localhost',
        DB_NAME: 'profiles',
        DB_USER: 'profiles',
        DB_PASSWORD: 'test-only',
        RABBITMQ_URI: 'amqp://profile:test-only@localhost:5679/profile-tests',
        SUPABASE_URL: 'https://supabase.example.test',
        SUPABASE_JWKS_URL: 'https://supabase.example.test/auth/v1/.well-known/jwks.json',
    };

    it('requires an explicit broker URI by default', () => {
        expect(() => validateEnvironment({ ...valid, RABBITMQ_URI: undefined })).toThrow('RABBITMQ_URI');
    });
    it('accepts Auth-compatible URL alias without changing Auth configuration', () => {
        expect(
            validateEnvironment({ ...valid, RABBITMQ_URI: undefined, RABBITMQ_URL: valid.RABBITMQ_URI }),
        ).toMatchObject({ RABBITMQ_URI: valid.RABBITMQ_URI });
    });
    it('rejects conflicting aliases', () => {
        expect(() => validateEnvironment({ ...valid, RABBITMQ_URL: valid.RABBITMQ_URI + 'other' })).toThrow(
            'conflicting',
        );
    });
    it.each(['http://profile:test@localhost', 'amqp://localhost', 'invalid'])(
        'rejects invalid URI %s',
        (RABBITMQ_URI) => {
            expect(() => validateEnvironment({ ...valid, RABBITMQ_URI })).toThrow('RABBITMQ_URI');
        },
    );
    it('requires AMQPS outside local environments', () => {
        expect(() => validateEnvironment({ ...valid, APP_ENV: 'production', DB_SSL: true })).toThrow('RABBITMQ_URI');
        expect(
            validateEnvironment({
                ...valid,
                APP_ENV: 'production',
                DB_SSL: true,
                RABBITMQ_URI: valid.RABBITMQ_URI.replace('amqp:', 'amqps:'),
            }),
        ).toMatchObject({ RABBITMQ_CONSUMER_ENABLED: true });
    });
    it.each([0, 2, 4])('rejects unsupported attempt limit %s', (RABBITMQ_MAX_ATTEMPTS) => {
        expect(() => validateEnvironment({ ...valid, RABBITMQ_MAX_ATTEMPTS })).toThrow('RABBITMQ_MAX_ATTEMPTS');
    });
    it('rejects topology drift and non-progressive delays', () => {
        expect(() => validateEnvironment({ ...valid, RABBITMQ_QUEUE: 'another-service' })).toThrow('RABBITMQ_QUEUE');
        expect(() =>
            validateEnvironment({
                ...valid,
                APP_ENV: 'test',
                RABBITMQ_RETRY_DELAY_1_MS: 100,
                RABBITMQ_RETRY_DELAY_2_MS: 50,
            }),
        ).toThrow('progressive');
        expect(() => validateEnvironment({ ...valid, RABBITMQ_RETRY_DELAY_1_MS: 10 })).toThrow(
            'RABBITMQ_RETRY_DELAY_1_MS',
        );
    });
});
