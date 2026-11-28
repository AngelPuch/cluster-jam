export function validateEnvironment(input: Record<string, unknown>): Record<string, unknown> {
    const result: Record<string, unknown> = {
        APP_ENV: 'development',
        HTTP_PORT: 8085,
        DB_PORT: 5432,
        DB_SSL: false,
        LOG_LEVEL: 'INFO',
        RABBITMQ_ENABLED: false,
        ...input,
    };
    if (!['development', 'test', 'staging', 'production'].includes(String(result.APP_ENV))) {
        throw new Error('Invalid configuration: APP_ENV');
    }
    for (const key of ['DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']) {
        if (typeof result[key] !== 'string' || !result[key].trim()) {
            throw new Error(`Invalid configuration: ${key}`);
        }
    }
    for (const key of ['HTTP_PORT', 'DB_PORT']) {
        const value = Number(result[key]);
        if (!Number.isInteger(value) || value < 1 || value > 65535) {
            throw new Error(`Invalid configuration: ${key}`);
        }
        result[key] = value;
    }
    if (![true, false, 'true', 'false'].includes(result.DB_SSL as boolean | string)) {
        throw new Error('Invalid configuration: DB_SSL');
    }
    result.DB_SSL = result.DB_SSL === true || result.DB_SSL === 'true';
    if (![true, false, 'true', 'false'].includes(result.RABBITMQ_ENABLED as boolean | string)) {
        throw new Error('Invalid configuration: RABBITMQ_ENABLED');
    }
    result.RABBITMQ_ENABLED = result.RABBITMQ_ENABLED === true || result.RABBITMQ_ENABLED === 'true';
    if (result.RABBITMQ_ENABLED) {
        try {
            if (typeof result.RABBITMQ_URI !== 'string') throw new Error();
            const uri = new URL(result.RABBITMQ_URI);
            if (
                !['amqp:', 'amqps:'].includes(uri.protocol) ||
                !uri.hostname ||
                !uri.username ||
                !uri.password ||
                uri.pathname.length < 2 ||
                uri.hash ||
                (['staging', 'production'].includes(String(result.APP_ENV)) && uri.protocol !== 'amqps:')
            ) {
                throw new Error();
            }
        } catch {
            throw new Error('Invalid configuration: RABBITMQ_URI');
        }
    }
    if (['staging', 'production'].includes(String(result.APP_ENV)) && !result.DB_SSL) {
        throw new Error('Invalid configuration: DB_SSL is required outside local development');
    }
    if (!['DEBUG', 'INFO', 'WARN', 'ERROR'].includes(String(result.LOG_LEVEL))) {
        throw new Error('Invalid configuration: LOG_LEVEL');
    }
    if (
        result.STRIPE_SECRET_KEY !== undefined &&
        result.STRIPE_SECRET_KEY !== '' &&
        (typeof result.STRIPE_SECRET_KEY !== 'string' || !/^(sk|rk)_test_[A-Za-z0-9]+$/.test(result.STRIPE_SECRET_KEY))
    ) {
        throw new Error('Invalid configuration: use a Stripe test key');
    }
    if (
        result.STRIPE_WEBHOOK_SECRET !== undefined &&
        result.STRIPE_WEBHOOK_SECRET !== '' &&
        (typeof result.STRIPE_WEBHOOK_SECRET !== 'string' || !/^whsec_[A-Za-z0-9]+$/.test(result.STRIPE_WEBHOOK_SECRET))
    ) {
        throw new Error('Invalid configuration: STRIPE_WEBHOOK_SECRET');
    }
    if (result.SUPABASE_URL !== undefined && result.SUPABASE_URL !== '') {
        try {
            if (typeof result.SUPABASE_URL !== 'string') throw new Error();
            const project = new URL(result.SUPABASE_URL);
            const local =
                ['development', 'test'].includes(String(result.APP_ENV)) &&
                ['localhost', '127.0.0.1', '[::1]'].includes(project.hostname);
            if (
                !(project.protocol === 'https:' || (local && project.protocol === 'http:')) ||
                project.username ||
                project.password ||
                project.href !== project.origin + '/'
            )
                throw new Error();
            const issuer = project.origin + '/auth/v1';
            const jwks = issuer + '/.well-known/jwks.json';
            if (
                (result.SUPABASE_ISSUER !== undefined && result.SUPABASE_ISSUER !== issuer) ||
                (result.SUPABASE_JWKS_URL !== undefined && result.SUPABASE_JWKS_URL !== jwks) ||
                (result.SUPABASE_AUDIENCE !== undefined && result.SUPABASE_AUDIENCE !== 'authenticated')
            )
                throw new Error();
            result.SUPABASE_URL = project.origin;
        } catch {
            throw new Error('Invalid configuration: trusted Supabase project');
        }
    }
    for (const key of ['SERVICE_VERSION', 'INSTANCE_ID']) {
        const value = result[key];
        if (value !== undefined && (typeof value !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9._+-]{0,127}$/.test(value))) {
            throw new Error(`Invalid configuration: ${key}`);
        }
    }
    return result;
}
