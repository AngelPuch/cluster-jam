import { Module } from '@nestjs/common';

import { AUTH_PROVIDER_PORT } from '../../application/ports/auth-provider.port';
import { SupabaseAuthAdapter } from './supabase-auth.adapter';

@Module({
    providers: [
        SupabaseAuthAdapter,
        {
            provide: AUTH_PROVIDER_PORT,
            useExisting: SupabaseAuthAdapter,
        },
    ],
    exports: [AUTH_PROVIDER_PORT],
})
export class SupabaseModule {}
