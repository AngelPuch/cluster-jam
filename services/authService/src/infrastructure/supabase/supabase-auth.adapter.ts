import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { createClient } from '@supabase/supabase-js';

import { AuthProviderPort } from '../../application/ports/auth-provider.port';

const SUPABASE_HEALTH_TIMEOUT_MS = 2_000;

@Injectable()
export class SupabaseAuthAdapter implements AuthProviderPort {
    private readonly client: ReturnType<typeof createClient>;
    private readonly healthUrl: string;
    private readonly publishableKey: string;

    constructor(private readonly configService: ConfigService) {
        const supabaseUrl =
            this.configService.getOrThrow<string>('SUPABASE_URL');

        this.publishableKey = this.configService.getOrThrow<string>(
            'SUPABASE_PUBLISHABLE_KEY',
        );

        this.client = createClient(supabaseUrl, this.publishableKey, {
            auth: {
                autoRefreshToken: false,
                persistSession: false,
                detectSessionInUrl: false,
            },
        });

        this.healthUrl = new URL('/auth/v1/health', supabaseUrl).toString();
    }

    async isAvailable(): Promise<boolean> {
        try {
            const response = await fetch(this.healthUrl, {
                method: 'GET',
                headers: {
                    apikey: this.publishableKey,
                },
                signal: AbortSignal.timeout(SUPABASE_HEALTH_TIMEOUT_MS),
            });

            return response.ok;
        } catch {
            return false;
        }
    }
}
