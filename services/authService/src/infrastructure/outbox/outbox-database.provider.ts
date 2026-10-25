import { ConfigService } from '@nestjs/config';
import { readFileSync } from 'node:fs';
import { Pool } from 'pg';

export const OUTBOX_DATABASE = Symbol('OUTBOX_DATABASE');

export function createOutboxDatabase(config: ConfigService): Pool | null {
  if (!config.getOrThrow<boolean>('OUTBOX_PUBLISHER_ENABLED')) return null;

  const connectionString = config.getOrThrow<string>('OUTBOX_DATABASE_URL');
  const url = new URL(connectionString);

  for (const key of ['sslmode', 'sslcert', 'sslkey', 'sslrootcert']) {
    if (url.searchParams.has(key)) {
      throw new Error('Configure outbox TLS using OUTBOX_DATABASE_SSL and CA_PATH.');
    }
  }
  const caPath = config.get<string>('OUTBOX_DATABASE_CA_PATH');
  const pool = new Pool({
    connectionString,
    max: 2,
    connectionTimeoutMillis: 3_000,
    idleTimeoutMillis: 10_000,
    statement_timeout: 3_000,
    query_timeout: 4_000,
    idle_in_transaction_session_timeout: 15_000,
    application_name: 'cluster-jam-auth-outbox',
    ssl: config.getOrThrow<boolean>('OUTBOX_DATABASE_SSL')
      ? {
          rejectUnauthorized: true,
          ...(caPath ? { ca: readFileSync(caPath, 'utf8') } : {}),
        }
      : false,
  });

  pool.on('error', () => undefined);
  return pool;
}
