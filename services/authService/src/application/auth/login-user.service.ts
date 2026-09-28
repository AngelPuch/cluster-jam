import { Inject, Injectable } from '@nestjs/common';

import {
    AUTH_PROVIDER_PORT,
    type AuthProviderPort,
    type LoginUserInput,
    type LoginUserResult,
} from '../ports/auth-provider.port';

@Injectable()
export class LoginUserService {
    constructor(
        @Inject(AUTH_PROVIDER_PORT)
        private readonly authProvider: AuthProviderPort,
    ) {}

    execute(input: LoginUserInput): Promise<LoginUserResult> {
        return this.authProvider.loginUser(input);
    }
}
