import { Inject, Injectable } from '@nestjs/common';

import {
    AUTH_PROVIDER_PORT,
    type AuthProviderPort,
    type RefreshSessionInput,
    type RefreshSessionResult,
} from '../ports/auth-provider.port';

@Injectable()
export class RefreshSessionService {
    constructor(
        @Inject(AUTH_PROVIDER_PORT)
        private readonly authProvider: AuthProviderPort,
    ) {}

    execute(input: RefreshSessionInput): Promise<RefreshSessionResult> {
        return this.authProvider.refreshSession(input);
    }
}
