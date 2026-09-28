import { Module } from '@nestjs/common';

import { RegisterUserService } from '../../../application/auth/register-user.service';
import { LoginUserService } from '../../../application/auth/login-user.service';
import { SupabaseModule } from '../../../infrastructure/supabase/supabase.module';
import { RegistrationController } from './registration.controller';
import { SessionController } from './session.controller';

@Module({
    imports: [SupabaseModule],
    controllers: [RegistrationController, SessionController],
    providers: [RegisterUserService, LoginUserService],
})
export class AuthModule {}
