import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { configureApiPrefix, createProfileOpenApiDocument } from '../interfaces/http/openapi/openapi.setup';

const contractPath = resolve(__dirname, '../../../../contracts/openapi/profile/v1/openapi.json');

function sortJson(value: unknown): unknown {
    if (Array.isArray(value)) return value.map(sortJson);
    if (typeof value !== 'object' || value === null) return value;
    return Object.fromEntries(
        Object.entries(value)
            .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
            .map(([key, item]) => [key, sortJson(item)]),
    );
}

async function run(): Promise<void> {
    const mode = process.argv[2];
    if (process.argv.length !== 3 || (mode !== '--write' && mode !== '--check'))
        throw new Error('Use --write or --check.');
    // Valid public/local configuration only for metadata compilation. Preview mode never
    // constructs controllers/providers, connects adapters, initializes or serves the app.
    Object.assign(process.env, {
        APP_ENV: 'test',
        HTTP_PORT: '8080',
        DB_HOST: '127.0.0.1',
        DB_PORT: '5432',
        DB_USER: 'openapi',
        DB_PASSWORD: 'unused-in-preview',
        DB_NAME: 'unused',
        DB_SSL: 'false',
        DB_PASSWORD_FILE: '',
        RABBITMQ_URI_FILE: '',
        RABBITMQ_URL_FILE: '',
        RABBITMQ_URI: '',
        RABBITMQ_URL: '',
        SUPABASE_URL: 'https://openapi.invalid',
        SUPABASE_JWKS_URL: 'https://openapi.invalid/auth/v1/.well-known/jwks.json',
        SUPABASE_ISSUER: 'https://openapi.invalid/auth/v1',
        SUPABASE_AUDIENCE: 'authenticated',
        RABBITMQ_CONSUMER_ENABLED: 'false',
        LOG_LEVEL: 'ERROR',
    });
    const { AppModule } = await import('../app.module.js');
    const app = await NestFactory.create(AppModule, { logger: false, abortOnError: false, preview: true });
    try {
        configureApiPrefix(app);
        const generated = JSON.stringify(sortJson(createProfileOpenApiDocument(app)), null, 2) + '\n';
        if (mode === '--check') {
            let committed: unknown;
            try {
                committed = JSON.parse(await readFile(contractPath, 'utf8')) as unknown;
            } catch (error) {
                if (!(
                    error instanceof SyntaxError ||
                    (typeof error === 'object' && error !== null && 'code' in error && error.code === 'ENOENT')
                ))
                    throw error;
            }
            if (JSON.stringify(sortJson(committed), null, 2) + '\n' !== generated)
                throw new Error('OpenAPI contract drift. Run npm run openapi:export.');
            process.stdout.write('Profile OpenAPI contract is current.\n');
        } else {
            await mkdir(dirname(contractPath), { recursive: true });
            await writeFile(contractPath, generated, 'utf8');
            process.stdout.write('Profile OpenAPI contract exported.\n');
        }
    } finally {
        await app.close();
    }
}

void run().catch((error: unknown) => {
    process.stderr.write(
        error instanceof Error && error.message.startsWith('OpenAPI contract drift')
            ? error.message + '\n'
            : 'Profile OpenAPI command failed.\n',
    );
    process.exitCode = 1;
});
