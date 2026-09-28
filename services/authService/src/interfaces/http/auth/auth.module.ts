import { Module } from '@nestjs/common';

import { LoginUserService } from '../../../application/auth/login-user.service';
import { RefreshSessionService } from '../../../application/auth/refresh-session.service';
import { RegisterUserService } from '../../../application/auth/register-user.service';
import { SupabaseModule } from '../../../infrastructure/supabase/supabase.module';
import { RegistrationController } from './registration.controller';
import { SessionController } from './session.controller';
import { SessionRenewalController } from './session-renewal.controller';

@Module({
    imports: [SupabaseModule],
    controllers: [
        RegistrationController,
        SessionController,
        SessionRenewalController,
    ],
    providers: [RegisterUserService, LoginUserService, RefreshSessionService],
})
export class AuthModule {}
