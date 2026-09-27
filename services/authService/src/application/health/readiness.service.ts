import { Inject, Injectable } from '@nestjs/common';

import {
    AUTH_PROVIDER_PORT,
    type AuthProviderPort,
} from '../ports/auth-provider.port';

@Injectable()
export class ReadinessService {
    constructor(
        @Inject(AUTH_PROVIDER_PORT)
        private readonly authProvider: AuthProviderPort,
    ) {}

    isReady(): Promise<boolean> {
        return this.authProvider.isAvailable();
    }
}
