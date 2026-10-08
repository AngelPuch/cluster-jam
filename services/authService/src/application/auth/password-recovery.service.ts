import { Inject, Injectable } from '@nestjs/common';

import {
    AUTH_PROVIDER_PORT,
    type AuthProviderPort,
    type RecoverPasswordInput,
} from '../ports/auth-provider.port';

@Injectable()
export class PasswordRecoveryService {
    constructor(
        @Inject(AUTH_PROVIDER_PORT)
        private readonly provider: AuthProviderPort,
    ) {}

    request(email: string): Promise<void> {
        return this.provider.requestPasswordRecovery(email);
    }

    recover(input: RecoverPasswordInput): Promise<void> {
        return this.provider.recoverPassword(input);
    }
}
