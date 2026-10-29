import { readFileSync } from 'node:fs';

import { environmentValidationSchema } from './environment.validation';

const SECRET_VARIABLES = [
  'SUPABASE_PUBLISHABLE_KEY',
  'OUTBOX_DATABASE_URL',
  'RABBITMQ_URL',
] as const;

export function validateEnvironment(input: Record<string, unknown>): Record<string, unknown> {
  const resolved = { ...input };
  for (const name of SECRET_VARIABLES) {
    const fileName = `${name}_FILE`;
    const path = resolved[fileName];
    if (path === undefined || path === '') continue;
    if (typeof path !== 'string' || (resolved[name] !== undefined && resolved[name] !== '')) {
      throw new Error('Auth secret configuration is invalid.');
    }
    try {
      const value = readFileSync(path, 'utf8').trim();
      if (!value) throw new Error('Empty secret.');
      resolved[name] = value;
    } catch {
      throw new Error('Auth secret file cannot be loaded.');
    }
  }
  const result = environmentValidationSchema.validate(resolved, {
    abortEarly: false,
    allowUnknown: true,
  });
  const value: unknown = result.value;
  if (result.error || typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error('Auth environment configuration is invalid.');
  }
  return value as Record<string, unknown>;
}
