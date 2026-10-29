import * as Joi from 'joi';

export const environmentValidationSchema = Joi.object({
  APP_ENV: Joi.string().valid('development', 'test', 'staging', 'production').required(),

  LOG_LEVEL: Joi.string().valid('DEBUG', 'INFO', 'WARN', 'ERROR').default('INFO'),

  SERVICE_VERSION: Joi.string()
    .pattern(/^[a-zA-Z0-9][a-zA-Z0-9.+-]{0,63}$/)
    .default('0.0.1'),

  INSTANCE_ID: Joi.string().pattern(/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/),

  HTTP_PORT: Joi.number().port().default(8080),

  SUPABASE_URL: Joi.string().uri().required(),

  SUPABASE_PUBLISHABLE_KEY: Joi.string().required(),

  SUPABASE_JWKS_URL: Joi.string().uri().required(),

  OUTBOX_PUBLISHER_ENABLED: Joi.boolean().default(true),

  OUTBOX_DATABASE_URL: Joi.string()
    .uri({ scheme: ['postgres', 'postgresql'] })
    .when('OUTBOX_PUBLISHER_ENABLED', { is: true, then: Joi.required() }),

  OUTBOX_DATABASE_SSL: Joi.boolean()
    .default(true)
    .when('APP_ENV', { is: Joi.valid('staging', 'production'), then: Joi.valid(true) }),

  OUTBOX_DATABASE_CA_PATH: Joi.string(),

  RABBITMQ_URL: Joi.string()
    .uri({ scheme: ['amqp', 'amqps'] })
    .when('OUTBOX_PUBLISHER_ENABLED', { is: true, then: Joi.required() })
    .when('APP_ENV', {
      is: Joi.valid('staging', 'production'),
      then: Joi.string().uri({ scheme: ['amqps'] }),
    }),
});
