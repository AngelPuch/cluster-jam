import { Module } from '@nestjs/common';

import { RegisterUserService } from '../../../application/auth/register-user.service';
import { SupabaseModule } from '../../../infrastructure/supabase/supabase.module';
import { RegistrationController } from './registration.controller';

@Module({
    imports: [SupabaseModule],
    controllers: [RegistrationController],
    providers: [RegisterUserService],
})
export class AuthModule {}
