import { Module } from '@nestjs/common';

import { LoginUserService } from '../../../application/auth/login-user.service';
import { RefreshSessionService } from '../../../application/auth/refresh-session.service';
import { RegisterUserService } from '../../../application/auth/register-user.service';
import { CurrentSessionService } from '../../../application/auth/current-session.service';
import { PasswordRecoveryService } from '../../../application/auth/password-recovery.service';

import { SupabaseModule } from '../../../infrastructure/supabase/supabase.module';
import { RegistrationController } from './registration.controller';
import { SessionController } from './session.controller';
import { SessionRenewalController } from './session-renewal.controller';
import { CurrentSessionController } from './current-session.controller';
import { PasswordRecoveryController } from './password-recovery.controller';

@Module({
    imports: [SupabaseModule],
    controllers: [
        RegistrationController,
        SessionController,
        SessionRenewalController,
        CurrentSessionController,
        PasswordRecoveryController,
    ],
    providers: [
        RegisterUserService,
        LoginUserService,
        RefreshSessionService,
        CurrentSessionService,
        PasswordRecoveryService,
    ],
})
export class AuthModule {}
