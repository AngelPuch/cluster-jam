export function validateEnvironment(environment: Record<string, unknown>): Record<string, unknown> {
    const result: Record<string, unknown> = {
        APP_ENV: 'development',
        HTTP_PORT: 8080,
        DB_PORT: 5432,
        DB_SSL: false,
        ...environment,
    };
    for (const key of ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME'] as const) {
        const value = result[key];
        if (typeof value !== 'string' || value.trim() === '') throw new Error(`Invalid configuration: ${key}`);
    }
    if (!['development', 'test', 'staging', 'production'].includes(String(result.APP_ENV))) {
        throw new Error('Invalid configuration: APP_ENV');
    }
    for (const key of ['HTTP_PORT', 'DB_PORT'] as const) {
        const value = Number(result[key]);
        if (!Number.isInteger(value) || value < 1 || value > 65535) throw new Error(`Invalid configuration: ${key}`);
        result[key] = value;
    }
    if (![true, false, 'true', 'false'].some((value) => value === result.DB_SSL)) {
        throw new Error('Invalid configuration: DB_SSL');
    }
    result.DB_SSL = result.DB_SSL === true || result.DB_SSL === 'true';
    if (['staging', 'production'].includes(String(result.APP_ENV)) && !result.DB_SSL) {
        throw new Error('Invalid configuration: DB_SSL must be enabled outside local development');
    }
    return result;
}
