import * as Joi from 'joi';

export const environmentValidationSchema = Joi.object({
    APP_ENV: Joi.string().valid('development', 'test', 'production').required(),

    HTTP_PORT: Joi.number().port().default(8080),

    SUPABASE_URL: Joi.string().uri().required(),

    SUPABASE_PUBLISHABLE_KEY: Joi.string().required(),

    SUPABASE_JWKS_URL: Joi.string().uri().required(),
});
