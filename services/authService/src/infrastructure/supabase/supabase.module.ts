import { Module } from '@nestjs/common';

import { AUTH_PROVIDER_PORT } from '../../application/ports/auth-provider.port';
import { CURRENT_SESSION_PORT } from '../../application/ports/current-session.port';
import { SupabaseAuthAdapter } from './supabase-auth.adapter';
import { SupabaseCurrentSessionAdapter } from './supabase-current-session.adapter';

@Module({
    providers: [
        SupabaseAuthAdapter,
        {
            provide: AUTH_PROVIDER_PORT,
            useExisting: SupabaseAuthAdapter,
        },
        SupabaseCurrentSessionAdapter,
        {
            provide: CURRENT_SESSION_PORT,
            useExisting: SupabaseCurrentSessionAdapter,
        },
    ],
    exports: [AUTH_PROVIDER_PORT, CURRENT_SESSION_PORT],
})
export class SupabaseModule {}
