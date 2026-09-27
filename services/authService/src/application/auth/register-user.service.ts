import { Inject, Injectable } from '@nestjs/common';

import {
    AUTH_PROVIDER_PORT,
    type AuthProviderPort,
    type RegisterUserInput,
    type RegisterUserResult,
} from '../ports/auth-provider.port';

@Injectable()
export class RegisterUserService {
    constructor(
        @Inject(AUTH_PROVIDER_PORT)
        private readonly authProvider: AuthProviderPort,
    ) {}

    execute(input: RegisterUserInput): Promise<RegisterUserResult> {
        return this.authProvider.registerUser(input);
    }
}
