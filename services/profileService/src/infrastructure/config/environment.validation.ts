import topology from '../messaging/profile-topology.json';
import { validateSecurityEnvironment } from './security-environment.validation';
import { resolveSecretFiles } from './secret-files';

export function validateDatabaseEnvironment(environment: Record<string, unknown>): Record<string, unknown> {
    const result: Record<string, unknown> = {
        APP_ENV: 'development',
        HTTP_PORT: 8080,
        DB_PORT: 5432,
        DB_SSL: false,
        ...resolveSecretFiles(environment, ['DB_PASSWORD']),
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
    if (
        result.DB_RUNTIME_ROLE !== undefined &&
        (typeof result.DB_RUNTIME_ROLE !== 'string' || !/^[a-z_][a-z0-9_]{0,62}$/.test(result.DB_RUNTIME_ROLE))
    ) {
        throw new Error('Invalid configuration: DB_RUNTIME_ROLE');
    }
    return result;
}

export function validateEnvironment(environment: Record<string, unknown>): Record<string, unknown> {
    const result = resolveSecretFiles(validateDatabaseEnvironment(environment), ['RABBITMQ_URI', 'RABBITMQ_URL']);
    const enabled = result.RABBITMQ_CONSUMER_ENABLED ?? true;
    if (![true, false, 'true', 'false'].some((value) => value === enabled)) {
        throw new Error('Invalid configuration: RABBITMQ_CONSUMER_ENABLED');
    }
    result.RABBITMQ_CONSUMER_ENABLED = enabled === true || enabled === 'true';
    if (result.RABBITMQ_URI && result.RABBITMQ_URL && result.RABBITMQ_URI !== result.RABBITMQ_URL) {
        throw new Error('Invalid configuration: conflicting RabbitMQ URI aliases');
    }
    result.RABBITMQ_URI ??= result.RABBITMQ_URL;
    if (result.RABBITMQ_CONSUMER_ENABLED || result.RABBITMQ_URI) {
        try {
            if (typeof result.RABBITMQ_URI !== 'string') throw new Error();
            const uri = new URL(result.RABBITMQ_URI);
            const secure = ['staging', 'production'].includes(String(result.APP_ENV));
            if (
                !(secure ? ['amqps:'] : ['amqp:', 'amqps:']).includes(uri.protocol) ||
                !uri.hostname ||
                !uri.username ||
                !uri.password
            )
                throw new Error();
        } catch {
            throw new Error('Invalid configuration: RABBITMQ_URI');
        }
    }
    const names: Record<string, string> = {
        RABBITMQ_EXCHANGE: topology.exchange,
        RABBITMQ_QUEUE: topology.queue,
        RABBITMQ_RETRY_EXCHANGE: topology.retryExchange,
        RABBITMQ_DLX: topology.deadLetterExchange,
        RABBITMQ_DLQ: topology.dlq,
        RABBITMQ_RETRY_QUEUE_1: topology.retries[0].queue,
        RABBITMQ_RETRY_QUEUE_2: topology.retries[1].queue,
    };
    for (const [key, value] of Object.entries(names)) {
        result[key] ??= value;
        if (result[key] !== value) throw new Error(`Invalid configuration: ${key} must match the versioned topology`);
    }
    result.RABBITMQ_MAX_ATTEMPTS = Number(result.RABBITMQ_MAX_ATTEMPTS ?? topology.maxAttempts);
    if (result.RABBITMQ_MAX_ATTEMPTS !== 3) throw new Error('Invalid configuration: RABBITMQ_MAX_ATTEMPTS');
    for (const [index, retry] of topology.retries.entries()) {
        const key = `RABBITMQ_RETRY_DELAY_${index + 1}_MS`;
        const value = Number(result[key] ?? retry.delayMs);
        if (
            !Number.isSafeInteger(value) ||
            value <= 0 ||
            value > 600000 ||
            (result.APP_ENV !== 'test' && value !== retry.delayMs)
        )
            throw new Error(`Invalid configuration: ${key}`);
        result[key] = value;
    }
    if (Number(result.RABBITMQ_RETRY_DELAY_2_MS) <= Number(result.RABBITMQ_RETRY_DELAY_1_MS)) {
        throw new Error('Invalid configuration: retry delays must be progressive');
    }
    result.LOG_LEVEL ??= 'INFO';
    if (!['DEBUG', 'INFO', 'WARN', 'ERROR'].includes(String(result.LOG_LEVEL)))
        throw new Error('Invalid configuration: LOG_LEVEL');
    for (const key of ['SERVICE_VERSION', 'INSTANCE_ID']) {
        if (
            result[key] !== undefined &&
            (typeof result[key] !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9._+-]{0,127}$/.test(result[key]))
        ) {
            throw new Error(`Invalid configuration: ${key}`);
        }
    }
    return validateSecurityEnvironment(result);
}
