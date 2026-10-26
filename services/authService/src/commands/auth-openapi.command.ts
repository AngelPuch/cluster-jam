import type { INestApplication } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';

import { JsonLogger } from '../infrastructure/observability/json-logger.service';
import { configureHttpApplication } from '../interfaces/http/http.setup';
import { createAuthOpenApiDocument } from '../interfaces/http/openapi/openapi.setup';

const CONTRACT_PATH = resolve(__dirname, '../../../../contracts/openapi/auth/v1/openapi.json');

function configureOfflineEnvironment(): void {
  Object.assign(process.env, {
    APP_ENV: 'test',
    HTTP_PORT: '8080',
    LOG_LEVEL: 'INFO',
    SERVICE_VERSION: '0.0.1',
    INSTANCE_ID: 'auth-openapi',
    SUPABASE_URL: 'https://openapi.invalid',
    SUPABASE_PUBLISHABLE_KEY: 'openapi-placeholder',
    SUPABASE_JWKS_URL: 'https://openapi.invalid/auth/v1/.well-known/jwks.json',
    OUTBOX_PUBLISHER_ENABLED: 'false',
    OUTBOX_DATABASE_URL: 'postgresql://openapi:placeholder@127.0.0.1:5432/unused',
    OUTBOX_DATABASE_SSL: 'false',
    RABBITMQ_URL: 'amqp://openapi:placeholder@127.0.0.1:5672/unused',
  });
  delete process.env.OUTBOX_DATABASE_CA_PATH;
}

function sortJson(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortJson);
  if (typeof value !== 'object' || value === null) return value;
  return Object.fromEntries(
    Object.entries(value)
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([key, item]) => [key, sortJson(item)]),
  );
}

function serializeDocument(value: unknown): string {
  return `${JSON.stringify(sortJson(value), null, 2)}\n`;
}

async function contractMatches(generated: string): Promise<boolean> {
  let committed: unknown;
  try {
    committed = JSON.parse(await readFile(CONTRACT_PATH, 'utf8')) as unknown;
  } catch (error) {
    if (
      error instanceof SyntaxError ||
      (typeof error === 'object' && error !== null && 'code' in error && error.code === 'ENOENT')
    )
      return false;
    throw error;
  }
  return serializeDocument(committed) === generated;
}

async function run(): Promise<void> {
  configureOfflineEnvironment();
  const logger = new JsonLogger();
  let app: INestApplication | undefined;
  try {
    const argumentsList = process.argv.slice(2);
    const mode = argumentsList[0];
    if (argumentsList.length !== 1 || (mode !== '--write' && mode !== '--check')) {
      throw new Error('Use --write or --check.');
    }

    const { AppModule } = await import('../app.module.js');
    app = await NestFactory.create(AppModule, { logger: false, abortOnError: false });
    configureHttpApplication(app, { enableOpenApi: false });
    const generated = serializeDocument(createAuthOpenApiDocument(app));

    if (mode === '--check') {
      if (!(await contractMatches(generated))) {
        logger.error({ event: 'auth.openapi.check.failed' });
        process.exitCode = 1;
        return;
      }
      logger.log({ event: 'auth.openapi.current' });
      return;
    }
    await mkdir(dirname(CONTRACT_PATH), { recursive: true });
    await writeFile(CONTRACT_PATH, generated, 'utf8');
    logger.log({ event: 'auth.openapi.exported' });
  } finally {
    await app?.close();
  }
}

void run().catch(() => {
  new JsonLogger().error({ event: 'auth.openapi.command.failed' });
  process.exitCode = 1;
});
